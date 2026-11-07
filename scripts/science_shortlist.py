#!/usr/bin/env python3
"""Research Shortlisting V1 with bounded OpenAlex abstract enrichment."""
import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

SUBJECTS = ("Physics", "Biology", "Chemistry", "Astronomy", "Computer Science")
ENRICHMENT_LIMIT = 100
FINAL_LIMIT = 30
OPENALEX_BATCH_SIZE = 50
MAX_RETRIES = 3
REQUEST_INTERVAL_SECONDS = 0.25
NON_RESEARCH_TYPES = {"editorial", "correction", "erratum", "retraction", "news", "letter", "commentary"}
EXPLICIT_NON_RESEARCH_TITLE = re.compile(
    r"^(?:erratum|correction to|author correction|retraction|corrigendum|expression of concern)\s*:",
    re.IGNORECASE,
)
REVIEW_TITLE = re.compile(r"\b(review|survey|perspective|overview|state[- ]of[- ]the[- ]art|tutorial)\b", re.IGNORECASE)
RESEARCH_TITLE = re.compile(
    r"\b(measurement|detection|characteri[sz]ation|synthesis|structure|dynamics|"
    r"evolution|association|regulation|quantif|analysis|observed|experiment|"
    r"sequencing|profiling|classification|optimization|model)\b", re.IGNORECASE
)


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]*>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value):
    return clean_text(value)


def parse_date(value):
    if not value:
        return None
    try:
        parts = [int(part) for part in str(value).split("-")]
        return date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    except (TypeError, ValueError):
        return None


def classify_paper(paper):
    title = normalize_title(paper.get("title"))
    record_type = str(paper.get("recordType") or "").lower().strip()
    if EXPLICIT_NON_RESEARCH_TITLE.search(title) or record_type in NON_RESEARCH_TYPES:
        return "non-research", "明确的勘误、撤稿、社论或评论记录"
    if REVIEW_TITLE.search(title) or "review" in record_type or "survey" in record_type:
        return "review", "标题或记录类型显示为综述/Survey/观点文章"
    return "original-research", None


def restore_inverted(index):
    if not isinstance(index, dict):
        return ""
    words = []
    for token, positions in index.items():
        for position in positions:
            words.append((position, token))
    return clean_text(" ".join(token for _, token in sorted(words)))


def retry_json(url, source_errors):
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "LearningOS-News/1.0 (editorial abstract enrichment)", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read()
            if content_type and "json" not in content_type.lower():
                raise ValueError("non-JSON response: " + content_type)
            return json.loads(raw), None
        except urllib.error.HTTPError as exc:
            body = " ".join(exc.read(500).decode("utf-8", errors="replace").split())
            last_error = f"HTTP {exc.code}: {body[:400]}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= MAX_RETRIES:
                break
            time.sleep(min(8, 2 ** attempt))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            if attempt >= MAX_RETRIES:
                break
            time.sleep(min(8, 2 ** attempt))
    source_errors.append(last_error or "unknown metadata error")
    return None, last_error


def fetch_openalex_batches(papers, source_errors):
    by_doi = {}
    request_count = 0
    for start in range(0, len(papers), OPENALEX_BATCH_SIZE):
        batch = papers[start:start + OPENALEX_BATCH_SIZE]
        filters = "|".join("doi:" + urllib.parse.quote("https://doi.org/" + p["doi"], safe="") for p in batch)
        url = "https://api.openalex.org/works?filter=" + filters + "&per-page=" + str(OPENALEX_BATCH_SIZE)
        request_count += 1
        payload, error = retry_json(url, source_errors)
        if payload is None:
            continue
        for item in payload.get("results", []):
            doi = str(item.get("doi") or "").lower().replace("https://doi.org/", "").strip()
            if not doi:
                continue
            by_doi[doi] = item
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return by_doi, request_count


def fetch_epmc(doi, source_errors):
    query = urllib.parse.quote('DOI:"' + doi + '"', safe="")
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + query + "&format=json"
    payload, error = retry_json(url, source_errors)
    if not payload:
        return None
    results = payload.get("resultList", {}).get("result", [])
    if not results:
        return None
    return clean_text(results[0].get("abstractText")) or None


def base_score(paper):
    paper_type, _ = classify_paper(paper)
    if paper_type == "non-research":
        return None
    score = 2 if paper_type == "original-research" else 1
    title_hits = sorted(set(m.group(0).lower() for m in RESEARCH_TITLE.finditer(normalize_title(paper.get("title")))))
    score += min(2, len(title_hits))
    return score


def score_candidate(paper):
    paper_type, type_reason = classify_paper(paper)
    if paper_type == "non-research":
        return None
    title_hits = sorted(set(m.group(0).lower() for m in RESEARCH_TITLE.finditer(normalize_title(paper.get("title")))))
    reasons = []
    questions = []
    score = 2 if paper_type == "original-research" else 1
    if paper_type == "review":
        reasons.append("标记为综述/Survey，不能当作新的实验成果")
        questions.append("需确认综述范围及其引用的原始研究")
    else:
        reasons.append("记录未显示为综述或明确非研究类型")
    if title_hits:
        score += min(2, len(title_hits))
        reasons.append("标题提供研究对象或方法线索：" + ", ".join(title_hits[:4]))
    else:
        questions.append("标题未显示清晰的研究问题或方法")
    abstract = paper.get("_abstract")
    if abstract:
        score += 3
        reasons.append("存在来自外部元数据源的真实摘要")
        confidence = "medium"
        if len(abstract) >= 400:
            score += 1
            confidence = "high"
    else:
        confidence = "low"
        questions.append("摘要不可用，不能据此判断研究结论、创新性或科学意义")
    if not parse_date(paper.get("publicationDate")):
        questions.append("发表日期精度或格式需要核验")
    if paper_type == "review":
        score = min(score, 5)
    return {
        "score": score,
        "confidence": confidence,
        "paperType": paper_type,
        "reasons": reasons,
        "questions": questions,
        "abstract": abstract,
        "abstractSource": paper.get("_abstractSource"),
        "typeReason": type_reason,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="science-candidates.json")
    parser.add_argument("--output", default="science-shortlist.json")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    papers = [p for p in payload.get("papers", []) if p.get("subject") in SUBJECTS]
    excluded = []
    eligible = []
    for paper in papers:
        paper_type, reason = classify_paper(paper)
        if paper_type == "non-research":
            excluded.append({"doi": paper.get("doi"), "title": normalize_title(paper.get("title")), "reason": reason})
        else:
            eligible.append(paper)

    enrichment_pool = sorted(
        eligible,
        key=lambda p: (base_score(p), parse_date(p.get("publicationDate")) or date.min, p.get("doi", "")),
        reverse=True,
    )[:ENRICHMENT_LIMIT]

    source_errors = []
    openalex_items, openalex_requests = fetch_openalex_batches(enrichment_pool, source_errors)
    openalex_matches = 0
    abstracts_fetched = 0
    epmc_attempts = 0
    epmc_matches = 0

    for paper in enrichment_pool:
        doi = str(paper.get("doi") or "").lower()
        item = openalex_items.get(doi)
        if item:
            openalex_matches += 1
            abstract = restore_inverted(item.get("abstract_inverted_index"))
            if abstract:
                paper["_abstract"] = abstract[:6000]
                paper["_abstractSource"] = "OpenAlex abstract_inverted_index"
                abstracts_fetched += 1

    for paper in enrichment_pool:
        if paper.get("_abstract") or paper.get("subject") != "Biology":
            continue
        epmc_attempts += 1
        abstract = fetch_epmc(paper.get("doi", ""), source_errors)
        if abstract:
            paper["_abstract"] = abstract[:6000]
            paper["_abstractSource"] = "Europe PMC abstractText"
            abstracts_fetched += 1
            epmc_matches += 1

    ranked = []
    for paper in eligible:
        result = score_candidate(paper)
        if result:
            ranked.append((result, paper))
    ranked.sort(
        key=lambda pair: (
            pair[0]["score"],
            pair[0]["confidence"] == "high",
            pair[0]["confidence"] == "medium",
            parse_date(pair[1].get("publicationDate")) or date.min,
            pair[1].get("doi", ""),
        ),
        reverse=True,
    )

    selected = []
    for result, paper in ranked[:FINAL_LIMIT]:
        selected.append({
            "doi": paper.get("doi"),
            "title": normalize_title(paper.get("title")),
            "titleOriginal": paper.get("titleOriginal") or paper.get("title"),
            "journal": paper.get("journal"),
            "subject": paper.get("subject"),
            "publicationDate": paper.get("publicationDate"),
            "publicationDateField": paper.get("publicationDateField"),
            "recordType": paper.get("recordType"),
            "paperType": result["paperType"],
            "url": paper.get("url") or ("https://doi.org/" + str(paper.get("doi"))),
            "abstract": result["abstract"],
            "abstractSource": result["abstractSource"],
            "abstractStatus": "available" if result["abstract"] else "unavailable",
            "priorityScore": result["score"],
            "screeningConfidence": result["confidence"],
            "screeningReasons": result["reasons"],
            "questionsForFurtherReview": result["questions"],
            "abstractUsageLimitations": "摘要来自第三方元数据，仅供编辑审查；不得自动作为正式新闻全文转载。",
            "screeningDisclaimer": "初筛分数仅用于后续审查排序，不代表研究质量、重要性或可信度。",
        })

    by_subject = {subject: sum(p["subject"] == subject for p in selected) for subject in SUBJECTS}
    score_distribution = defaultdict(int)
    confidence_distribution = defaultdict(int)
    for p in selected:
        score_distribution[str(p["priorityScore"])] += 1
        confidence_distribution[p["screeningConfidence"]] += 1

    output = {
        "schemaVersion": "1.2",
        "kind": "science_research_shortlist",
        "status": "ready_for_editorial_review",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {"file": args.input, "collectorStatus": payload.get("status"), "collectorCount": payload.get("count"), "collectorCollectedAt": payload.get("collectedAt")},
        "rules": {
            "subjects": list(SUBJECTS),
            "enrichmentLimit": ENRICHMENT_LIMIT,
            "finalLimit": FINAL_LIMIT,
            "journalPrestigeUsedAsImportance": False,
            "abstractPolicy": "OpenAlex 优先；生物医学候选在 OpenAlex 无摘要时尝试 Europe PMC；没有摘要则为 null。",
        },
        "statistics": {
            "inputCandidates": len(papers),
            "eligibleCandidates": len(eligible),
            "excluded": len(excluded),
            "enrichmentPool": len(enrichment_pool),
            "openAlexRequests": openalex_requests,
            "openAlexMatches": openalex_matches,
            "epmcRequests": epmc_attempts,
            "epmcMatches": epmc_matches,
            "abstractsFetched": abstracts_fetched,
            "abstractFetchRate": round(abstracts_fetched / len(enrichment_pool), 4) if enrichment_pool else 0,
            "sourceErrors": source_errors,
            "bySubject": by_subject,
            "scoreDistribution": dict(score_distribution),
            "confidenceDistribution": dict(confidence_distribution),
            "selected": len(selected),
        },
        "papers": selected,
        "excluded": excluded,
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["statistics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
