#!/usr/bin/env python3
"""Deterministic publication preflight; never trusts JSON as human release authorization."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
try:
    from scripts import semantic_review_gate as semantic
    from scripts import science_quality_gate as quality
except ModuleNotFoundError:
    import semantic_review_gate as semantic
    import science_quality_gate as quality

def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))

def evaluate(draft, review, editions_dir):
    blockers=[]
    try:
        quality.check_evidence(draft["articles"][0])
        for article in draft["articles"][1:]: quality.check_evidence(article)
        quality.duplicates_check = None
        evidence_valid=True
    except Exception as exc:
        evidence_valid=False; blockers.append("evidence_integrity_failed: "+str(exc))
    try:
        semantic_result=semantic.validate(draft,review)
        semantic_valid=True
    except Exception as exc:
        semantic_result={}; semantic_valid=False; blockers.append("semantic_review_invalid: "+str(exc))
    if review.get("reviewStatus")!="approved": blockers.append("editorial_review_pending")
    if any(c.get("verificationStatus") in semantic.BLOCKING for c in review.get("claims",[])): blockers.append("blocking_claim_status")
    if any(a.get("status")!="ApprovedForHumanReview" for a in draft.get("articles",[])): blockers.append("article_not_ready_for_human_review")
    seen=set()
    for article in draft.get("articles",[]):
        if article.get("id") in seen: blockers.append("duplicate_article_id")
        seen.add(article.get("id"))
        for p in Path(editions_dir).rglob("*.json") if Path(editions_dir).exists() else []:
            data=load(p)
            if any(old.get("doi","").lower()==article.get("doi","").lower() for old in data.get("articles",[])): blockers.append("doi_already_published")
    blockers.append("release_authorization_requires_external_github_protection")
    return {"draft_valid":draft.get("schemaVersion")=="2.0","evidence_valid":evidence_valid,"semantic_review_valid":semantic_valid,"editorial_approved":bool(semantic_result.get("editorial_approved")),"publication_eligible":False,"release_authorized":False,"blockers":sorted(set(blockers))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--draft",required=True); ap.add_argument("--review",required=True); ap.add_argument("--editions-dir",default="editions"); ap.add_argument("--output",required=True); args=ap.parse_args()
    result=evaluate(load(args.draft),load(args.review),args.editions_dir)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
