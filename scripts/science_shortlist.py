#!/usr/bin/env python3
"""Explainable research shortlisting. Priority only; not a quality verdict."""
import argparse
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

SUBJECTS = ("Physics", "Biology", "Chemistry", "Astronomy", "Computer Science")
MAX_PER_SUBJECT = 6
MIN_SCORE = 3
ABSTRACT_FETCH_LIMIT = 200
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
    r"sequencing|profiling|classification|optimization|model)\b",
    re.IGNORECASE,
)
ABSTRACT_RE = re.compile(r"<jats:abstract[^>]*>(.*?)</jats:abstract>|<abstract[^>]*>(.*?)</abstract>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = TAG_RE.sub("", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


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


def abstract_from_crossref(doi):
    email = os.environ.get("CROSSREF_EMAIL", "").strip()
    params = {}
    if email:
        params["mailto"] = email
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="") + (
        "?" + urllib.parse.urlencode(params) if params else ""
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "LearningOS-News/1.0 (research shortlisting)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            item = json.load(response).get("message", {})
        raw = item.get("abstract")
        if not raw:
            return None, None, "Crossref metadata does not provide an abstract"
        text = clean_text(raw)
        if not text:
            return None, None, "Crossref abstract is empty after cleaning"
        return text[:4000], "Crossref DOI metadata", None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, None, f"Crossref abstract lookup failed: {type(exc).__name__}"


def enrich_abstracts(papers):
    enriched = 0
    attempted = 0
    for paper in papers[:ABSTRACT_FETCH_LIMIT]:
        attempted += 1
        abstract, source, error = abstract_from_crossref(paper.get("doi", ""))
        if abstract:
            paper["_abstract"] = abstract
            paper["_abstractSource"] = source
            enriched += 1
        else:
            paper["_abstractError"] = error
        time.sleep(REQUEST_INTERVAL_SECONDS)
    return attempted, enriched


def score_candidate(paper):
    title = normalize_title(paper.get("title"))
    abstract = paper.get("_abstract") or ""
    paper_type, type_reason = classify_paper(paper)
    evidence = []
    questions = []
    score = 0

    if paper_type == "original-research":
        score += 2
        evidence.append("记录未显示为综述或非研究类型")
    elif paper_type == "review":
        score += 1
        evidence.append("标记为综述/Survey，适合背景审查而非新实验结论")
        questions.append("需确认是否为综述而非原创实验研究")
    else:
        return None

    title_hits = sorted(set(m.group(0).lower() for m in RESEARCH_TITLE.finditer(title)))
    if title_hits:
        score += min(2, len(title_hits))
        evidence.append("标题含研究对象或方法线索：" + ", ".join(title_hits[:4]))
    else:
        questions.append("标题未显示清晰的研究问题或方法")

    if abstract:
        score += 3
        evidence.append("已获得可清洗的摘要，可进行下一阶段内容核查")
        confidence = "medium"
        if len(abstract) >= 400:
            score += 1
            confidence = "high"
    else:
        questions.append("摘要不可用，不能据此判断研究结论、创新性或科学意义")
        confidence = "low"

    if not parse_date(paper.get("publicationDate")):
        questions.append("发表日期精度或格式需要核验")

    if paper_type == "review":
        score = min(score, 5)

    return {
        "score": score,
        "confidence": confidence,
        "paperType": paper_type,
        "evidence": evidence,
        "questions": questions,
        "abstract": abstract or None,
        "abstractSource": paper.get("_abstractSource"),
        "typeReason": type_reason,
    }


def load_candidates(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("science-candidates.json 的 papers 必须是数组")
    return payload, [p for p in papers if p.get("subject") in SUBJECTS]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="science-candidates.json")
    parser.add_argument("--output", default="science-shortlist.json")
    args = parser.parse_args()

    payload, papers = load_candidates(args.input)
    excluded = []
    eligible = []
    for paper in papers:
        paper_type, reason = classify_paper(paper)
        if paper_type == "non-research":
            excluded.append({"doi": paper.get("doi"), "title": normalize_title(paper.get("title")), "reason": reason})
        else:
            eligible.append(paper)

    attempted, fetched = enrich_abstracts(eligible)
    grouped = defaultdict(list)
    for paper in eligible:
        result = score_candidate(paper)
        if result and result["score"] >= MIN_SCORE:
            grouped[paper["subject"]].append((result, paper))

    selected = []
    by_subject = {}
    for subject in SUBJECTS:
        ranked = sorted(
            grouped.get(subject, []),
            key=lambda pair: (
                pair[0]["score"],
                pair[0]["confidence"] == "high",
                pair[0]["confidence"] == "medium",
                parse_date(pair[1].get("publicationDate")) or date.min,
                pair[1].get("doi", ""),
            ),
            reverse=True,
        )[:MAX_PER_SUBJECT]
        by_subject[subject] = {"inputEligible": sum(1 for p in eligible if p.get("subject") == subject), "selected": len(ranked), "max": MAX_PER_SUBJECT}
        for result, paper in ranked:
            selected.append({
                "doi": paper.get("doi"),
                "title": normalize_title(paper.get("title")),
                "titleOriginal": paper.get("titleOriginal") or paper.get("title"),
                "journal": paper.get("journal"),
                "subject": subject,
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
                "screeningReasons": result["evidence"],
                "questionsForFurtherReview": result["questions"],
                "screeningDisclaimer": "初筛分数仅用于后续审查排序，不代表研究质量、重要性或可信度。",
            })

    selected.sort(key=lambda p: (SUBJECTS.index(p["subject"]), -p["priorityScore"], p["doi"] or ""))
    scores = defaultdict(int)
    confidences = defaultdict(int)
    for paper in selected:
        scores[str(paper["priorityScore"])] += 1
        confidences[paper["screeningConfidence"]] += 1

    output = {
        "schemaVersion": "1.1",
        "kind": "science_research_shortlist",
        "status": "ready_for_editorial_review",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "file": args.input,
            "collectorStatus": payload.get("status"),
            "collectorCount": payload.get("count"),
            "collectorCollectedAt": payload.get("collectedAt"),
        },
        "rules": {
            "subjects": list(SUBJECTS),
            "maxPerSubject": MAX_PER_SUBJECT,
            "minimumScore": MIN_SCORE,
            "journalPrestigeUsedAsImportance": False,
            "abstractPolicy": "优先读取 Crossref DOI 元数据；无摘要则明确标记，不编造",
            "exclusionPolicy": "仅排除明确文献类型或标题开头的勘误/撤稿/社论等",
        },
        "statistics": {
            "inputCandidates": len(papers),
            "eligibleCandidates": len(eligible),
            "excluded": len(excluded),
            "selected": len(selected),
            "abstractLookupAttempted": attempted,
            "abstractsFetched": fetched,
            "abstractFetchRate": round(fetched / attempted, 4) if attempted else 0,
            "scoreDistribution": dict(scores),
            "confidenceDistribution": dict(confidences),
            "bySubject": by_subject,
        },
        "papers": selected,
        "excluded": excluded,
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["statistics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
