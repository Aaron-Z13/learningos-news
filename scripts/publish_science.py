#!/usr/bin/env python3
"""Dry-run only release planner. It deliberately has no write-to-editions mode."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
try:
    from scripts import publication_eligibility as eligibility
    from scripts import semantic_review_gate as semantic
except ModuleNotFoundError:
    import publication_eligibility as eligibility
    import semantic_review_gate as semantic

def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def canonical(obj): return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def candidate_fingerprint(candidate):
    value=dict(candidate); value.pop("candidateFingerprint",None)
    return hashlib.sha256(canonical(value).encode()).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--candidate",required=True); ap.add_argument("--draft",required=True); ap.add_argument("--review",required=True); ap.add_argument("--editions-dir",default="editions"); ap.add_argument("--manifest",default="manifest.json"); ap.add_argument("--dry-run",action="store_true",required=True); ap.add_argument("--output",required=True); args=ap.parse_args()
    candidate,draft,review=load(args.candidate),load(args.draft),load(args.review)
    manifest=load(args.manifest)
    result=eligibility.evaluate(draft,review,args.editions_dir)
    candidate_ok=(candidate.get("draftFingerprint")==semantic.fingerprint(draft) and candidate.get("candidateFingerprint")==candidate_fingerprint(candidate) and candidate.get("candidateStatus")!="authorized" and isinstance(manifest,dict))
    blockers=list(result["blockers"])
    if not candidate_ok: blockers.append("candidate_integrity_invalid")
    plan={"dry_run":True,"candidate_valid":candidate_ok,"publication_eligible":result["publication_eligible"],"would_write":[],"would_update_manifest":False,"blockers":sorted(set(blockers)),"edition_preview":{"date":candidate.get("intendedEditionDate"),"articleIds":candidate.get("articleIds",[])}}
    Path(args.output).write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(plan,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
