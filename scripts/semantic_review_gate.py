#!/usr/bin/env python3
"""Validate semantic-review records without pretending to perform semantic science review."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

CLAIM_STATUSES={"unreviewed","supported","partially_supported","unsupported","contradicted","insufficient_evidence"}
REVIEW_STATUSES={"pending_review","changes_requested","approved","rejected"}
BLOCKING={"unreviewed","unsupported","contradicted","insufficient_evidence"}

class ReviewError(Exception): pass

def load(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e: raise ReviewError(f"无法读取JSON {path}: {e}")

def fingerprint(draft):
    return hashlib.sha256(json.dumps(draft,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def validate(draft, review):
    if draft.get("kind")!="science_editorial_draft" or draft.get("schemaVersion")!="2.0": raise ReviewError("只接受 V2 science editorial draft")
    if review.get("schemaVersion")!="1.0" or review.get("kind")!="science_semantic_review": raise ReviewError("语义审核记录 Schema 无效")
    if review.get("draftId")!=draft.get("draftId"): raise ReviewError("审核记录未绑定该 Draft")
    actual=fingerprint(draft)
    if review.get("draftFingerprint")!=actual: raise ReviewError("Draft 已修改，旧审核批准失效")
    articles={a["id"]:a for a in draft.get("articles",[])}
    claim_map={c["claimId"]:c for a in draft["articles"] for c in a.get("claims",[])}
    evidence_map={e["evidenceId"]:e for a in draft["articles"] for e in a.get("evidence",[])}
    seen=set()
    for c in review.get("claims",[]):
        cid=c.get("claimId")
        if cid in seen or cid not in claim_map: raise ReviewError(f"审核记录引用不存在或重复的 Claim: {cid}")
        seen.add(cid)
        if c.get("verificationStatus") not in CLAIM_STATUSES: raise ReviewError(f"非法语义状态: {cid}")
        for ref in c.get("evidenceRefs",[]):
            if ref not in evidence_map: raise ReviewError(f"Claim {cid} 引用不存在的 Evidence: {ref}")
        if not isinstance(c.get("reviewer"),str) or not c["reviewer"].strip() or not isinstance(c.get("reviewedAt"),str) or not c["reviewedAt"].strip():
            if c.get("verificationStatus")!="unreviewed": raise ReviewError(f"非 unreviewed Claim 缺少真实 reviewer/timestamp: {cid}")
        if c.get("verificationStatus")=="supported" and c.get("verificationMethod","").lower() in {"string_similarity","automatic","auto"}:
            raise ReviewError(f"禁止用字符串相似度自动支持 Claim: {cid}")
        q=c.get("quantitativeCheck") or {}
        if c.get("claimType")=="quantitative" and c.get("verificationStatus")!="unreviewed" and q.get("status")!="checked": raise ReviewError(f"定量 Claim 未完成明确数值检查记录: {cid}")
    if seen != set(claim_map): raise ReviewError("审核记录未覆盖全部 Claim")
    coverage={e.get("evidenceId"):e for e in review.get("evidenceCoverage",[])}
    for eid,e in evidence_map.items():
        x=coverage.get(eid)
        if not x: raise ReviewError(f"缺少 Evidence coverage: {eid}")
        if x.get("evidenceType") in {"metadata_abstract","publisher_abstract","preprint_abstract"} and x.get("level") not in {"L0","L1"}: raise ReviewError(f"摘要证据不得标为 L2/L3: {eid}")
        if x.get("level") in {"L2","L3"} and (not x.get("locator") or not x.get("checkedScope")): raise ReviewError(f"L2/L3 缺少可复核定位: {eid}")
        if x.get("accessStatus")=="failed" and x.get("level") in {"L2","L3"}: raise ReviewError(f"访问失败的 Evidence 不得标为 L2/L3: {eid}")
    decision=review.get("reviewStatus")
    if decision not in REVIEW_STATUSES or review.get("review",{}).get("decision")!=decision: raise ReviewError("审核状态不一致或非法")
    r=review.get("review",{})
    if decision=="approved":
        if not r.get("reviewerId") or not r.get("reviewTimestamp"): raise ReviewError("approved 缺少真实 reviewer/timestamp")
        if any(c.get("verificationStatus") in BLOCKING for c in review["claims"]): raise ReviewError("存在阻断性 Claim，不得 approved")
    eligible=decision=="approved" and draft["articles"][0].get("status")=="ApprovedForHumanReview" and not any(c.get("verificationStatus") in BLOCKING for c in review["claims"])
    return {"draft_valid":True,"semantic_review_valid":True,"publication_eligible":eligible,"reviewStatus":decision,"semanticFactCheck":"requires_human_reviewer"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--draft",required=True); ap.add_argument("--review",required=True); ap.add_argument("--output",required=True)
    args=ap.parse_args()
    try:
        result=validate(load(args.draft),load(args.review))
    except ReviewError as e: print("SEMANTIC_REVIEW_FAILED: "+str(e),file=sys.stderr); return 1
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
