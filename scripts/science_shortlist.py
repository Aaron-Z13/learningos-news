#!/usr/bin/env python3
"""Explainable first-pass shortlist for Crossref science candidates.

This is prioritization only. It does not assert novelty, importance, or validity.
"""
import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

SUBJECTS = ("Physics", "Biology", "Chemistry", "Astronomy", "Computer Science")
TARGET_PER_SUBJECT = 5
MIN_PER_SUBJECT = 4
MAX_PER_SUBJECT = 6

NON_RESEARCH_PATTERNS = (
    r"^editorial$",
    r"^commentary$",
    r"^correction$",
    r"^erratum$",
    r"^corrigendum$",
    r"^news$",
    r"^letter$",
    r"^retraction$",
    r"^expression of concern$",
)
NON_RESEARCH_TITLE = re.compile(
    r"\b(editorial|correction|erratum|corrigendum|news|commentary|perspective|"
    r"retraction|expression of concern|in memoriam|obituary)\b",
    re.IGNORECASE,
)
RESEARCH_TYPE_HINTS = {
    "journal-article",
    "research-article",
    "article",
    "original-research",
}
QUESTION_HINTS = re.compile(
    r"\b(effect|mechanism|structure|dynamics|evolution|measurement|detection|"
    r"characteri[sz]ation|synthesis|design|discovery|analysis|model|observed|"
    r"quantif|intervention|association|regulation|conservation|classification)\b",
    re.IGNORECASE,
)
INNOVATION_HINTS = re.compile(
    r"\b(new|novel|first|high[- ]resolution|single[- ]cell|large[- ]scale|"
    r"deep learning|machine learning|genome[- ]wide|multi[- ]modal|precision|"
    r"unprecedented|framework|platform|method|approach|atlas|survey)\b",
    re.IGNORECASE,
)
SIGNIFICANCE_HINTS = re.compile(
    r"\b(implications?|enables?|reveals?|establishes?|provides?|understanding|"
    r"therapeutic|climate|cosmolog|fundamental|translat|application)\b",
    re.IGNORECASE,
)


def parse_date(value):
    if not value:
        return None
    try:
        parts = [int(part) for part in str(value).split("-")]
        return date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    except (TypeError, ValueError):
        return None


def text(value):
    if isinstance(value, list):
        return " ".join(str(part) for part in value)
    return str(value or "").strip()


def normalize_title(value):
    import html
    value = html.unescape(text(value))
    value = re.sub(r"<[^>]*>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def abstract_info(paper):
    abstract = paper.get("abstract") or paper.get("abstractText")
    if abstract:
        return {"text": text(abstract), "source": paper.get("abstractSource") or "science-candidates.json"}
    return {"text": "", "source": None}


def classify_exclusion(paper):
    title = normalize_title(paper.get("title"))
    record_type = text(paper.get("recordType")).lower()
    if NON_RESEARCH_TITLE.search(title):
        return "标题含社论、勘误、新闻评论或撤稿等非研究性标记"
    if any(re.search(pattern, record_type) for pattern in NON_RESEARCH_PATTERNS):
        return "记录类型属于非研究性内容"
    return None


def score_candidate(paper):
    title = text(paper.get("title"))
    abstract = abstract_info(paper)
    body = title + " " + abstract["text"]
    reasons = []
    questions = []
    score = 0

    if text(paper.get("recordType")).lower() in RESEARCH_TYPE_HINTS:
        score += 2
        reasons.append("记录类型为期刊研究文章")
    else:
        questions.append("记录类型不是常见原创研究类型，需要核对文章性质")

    question_hits = sorted(set(m.group(0).lower() for m in QUESTION_HINTS.finditer(body)))
    innovation_hits = sorted(set(m.group(0).lower() for m in INNOVATION_HINTS.finditer(body)))
    significance_hits = sorted(set(m.group(0).lower() for m in SIGNIFICANCE_HINTS.finditer(body)))

    if question_hits:
        score += 2
        reasons.append("标题或摘要出现明确研究问题/对象线索：" + ", ".join(question_hits[:4]))
    else:
        questions.append("标题或摘要未显示清晰的研究问题，需要人工核对")

    if innovation_hits:
        score += 2
        reasons.append("出现可能的创新方法、数据或发现线索：" + ", ".join(innovation_hits[:4]))
    else:
        questions.append("缺少明确创新性线索，不能仅凭期刊判断")

    if significance_hits:
        score += 1
        reasons.append("出现潜在科学意义或应用线索：" + ", ".join(significance_hits[:3]))

    if abstract["text"]:
        score += 1
        reasons.append("候选数据中存在摘要，可进行下一阶段核查")
    else:
        questions.append("未提供摘要，需通过合法元数据接口或原文补充；本程序未臆造摘要")

    if parse_date(paper.get("publicationDate")):
        score += 1
    else:
        questions.append("发表日期精度或格式需要核验")

    return score, reasons, questions, abstract


def load_candidates(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("science-candidates.json 的 papers 必须是数组")
    return payload, [paper for paper in papers if paper.get("subject") in SUBJECTS]


def shortlist(payload, papers):
    grouped = defaultdict(list)
    excluded = []
    for paper in papers:
        exclusion = classify_exclusion(paper)
        if exclusion:
            excluded.append({"doi": paper.get("doi"), "title": normalize_title(paper.get("title")), "reason": exclusion})
            continue
        score, reasons, questions, abstract = score_candidate(paper)
        item = {
            "score": score,
            "paper": paper,
            "reasons": reasons,
            "questions": questions,
            "abstract": abstract,
        }
        grouped[paper["subject"]].append(item)

    selected = []
    subject_stats = {}
    for subject in SUBJECTS:
        ranked = sorted(
            grouped.get(subject, []),
            key=lambda item: (
                item["score"],
                parse_date(item["paper"].get("publicationDate")) or date.min,
                item["paper"].get("doi", ""),
            ),
            reverse=True,
        )
        chosen = ranked[:MAX_PER_SUBJECT]
        # Prefer the configured target; fewer are allowed when the pool is exhausted.
        chosen = chosen[:TARGET_PER_SUBJECT]
        subject_stats[subject] = {
            "inputCandidates": len(grouped.get(subject, [])),
            "selected": len(chosen),
            "target": TARGET_PER_SUBJECT,
            "minimum": MIN_PER_SUBJECT,
            "qualityNote": (
                "候选不足或质量线索不足时不强行凑数"
                if len(chosen) < MIN_PER_SUBJECT else
                "按可解释规则选取，仍需后续人工核查"
            ),
        }
        for item in chosen:
            paper = item["paper"]
            selected.append({
                "doi": paper.get("doi"),
                "title": paper.get("title"),
                "titleOriginal": paper.get("titleOriginal") or paper.get("title"),
                "journal": paper.get("journal"),
                "subject": subject,
                "publicationDate": paper.get("publicationDate"),
                "publicationDateField": paper.get("publicationDateField"),
                "recordType": paper.get("recordType"),
                "url": paper.get("url"),
                "abstract": item["abstract"]["text"] or None,
                "abstractSource": item["abstract"]["source"],
                "abstractStatus": "available" if item["abstract"]["text"] else "unavailable",
                "priorityScore": item["score"],
                "screeningReasons": item["reasons"],
                "questionsForFurtherReview": item["questions"],
                "screeningDisclaimer": (
                    "初筛分数仅用于安排后续审查优先级，不代表研究质量、重要性或可信度。"
                ),
            })

    selected.sort(key=lambda item: (SUBJECTS.index(item["subject"]), -item["priorityScore"], item["doi"] or ""))
    return selected, excluded, subject_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="science-candidates.json")
    parser.add_argument("--output", default="science-shortlist.json")
    args = parser.parse_args()

    payload, papers = load_candidates(args.input)
    selected, excluded, subject_stats = shortlist(payload, papers)
    output = {
        "schemaVersion": "1.0",
        "kind": "science_research_shortlist",
        "status": "ready_for_editorial_review",
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "source": {
            "file": args.input,
            "collectorStatus": payload.get("status"),
            "collectorCount": payload.get("count"),
            "collectorCollectedAt": payload.get("collectedAt"),
        },
        "rules": {
            "subjects": list(SUBJECTS),
            "targetPerSubject": TARGET_PER_SUBJECT,
            "maxPerSubject": MAX_PER_SUBJECT,
            "excludes": ["社论", "勘误", "新闻评论", "撤稿及相关记录"],
            "journalPrestigeUsedAsImportance": False,
            "abstractPolicy": "只使用输入中已有摘要；没有摘要明确标注，不生成摘要或结论",
        },
        "statistics": {
            "inputCandidates": len(papers),
            "selected": len(selected),
            "excluded": len(excluded),
            "bySubject": subject_stats,
        },
        "papers": selected,
        "excluded": excluded,
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["statistics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
