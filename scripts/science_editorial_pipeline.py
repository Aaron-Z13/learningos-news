#!/usr/bin/env python3
import argparse,json,re
from pathlib import Path
from datetime import datetime,timezone
SUBJECTS=["Physics","Biology","Chemistry","Astronomy","Computer Science"]; STATUSES=["Draft","Reviewed","ApprovedForHumanReview","Published","Rejected"]
def load(p): return json.loads(Path(p).read_text())
def select(pkg,limit=6):
 seen=set(); ranked=[]
 for p in pkg.get("papers",[]):
  d=p.get("doi","").lower()
  if not d or d in seen: continue
  seen.add(d); title=(p.get("title") or "").lower()
  c={"scientificSignificanceHint":1 if p.get("abstract") else 0,"noveltyHint":1 if any(x in title for x in ("measurement","framework","observation","dynamics")) else 0,"publicRelevanceHint":1 if p.get("subject") in ("Biology","Physics") else 0,"evidenceStrength":(2 if p.get("verifiedFields",{}).get("doi") else 0)+(1 if p.get("fullTextAvailable") else 0),"recency":1,"diversityBonus":1 if p.get("subject") in SUBJECTS else 0}
  ranked.append((sum(c.values()),p,c))
 ranked.sort(key=lambda x:(-x[0],x[1].get("publicationDate",""),x[1].get("doi","")))
 chosen=[]; subjects=set()
 for score,p,c in ranked:
  if len(chosen)>=limit: break
  if p.get("subject") not in subjects or len(chosen)>=min(limit,len(SUBJECTS)):
   chosen.append({"doi":p["doi"],"title":p.get("title"),"subject":p.get("subject"),"score":score,"scoreComponents":c,"rationale":"确定性元数据预排序；不代表科学质量或重要性。","uncertainty":["尚未完成独立全文事实核查。"]}); subjects.add(p.get("subject"))
 return {"kind":"science_selection_report","generatedAt":datetime.now(timezone.utc).isoformat(),"method":"deterministic_metadata_preranking","selected":chosen,"excludedCount":max(0,len(ranked)-len(chosen)),"disclaimer":"评分仅安排编辑优先级，不证明重要性、创新性或可信度。"}
def evidence_map(pkg):
 return {f'{p.get("doi")}#e{i}':(p,e) for p in pkg.get("papers",[]) for i,e in enumerate(p.get("evidence",[]))}
def review(d,pkg):
 if d.get("editorialStatus") not in STATUSES:return ["invalid editorial status"]
 pm={p.get("doi"):p for p in pkg.get("papers",[])}; pub=d.get("publication",{}); p=pm.get(pub.get("doi")); errs=[]
 if not p: errs.append("DOI absent from Evidence package")
 elif pub.get("title")!=p.get("title") or pub.get("journal")!=p.get("journal"): errs.append("publication metadata mismatch")
 em=evidence_map(pkg)
 for c in d.get("claims",[]):
  if not c.get("evidenceRefs"): errs.append(f'{c.get("claimId")}: missing evidence')
  for ref in c.get("evidenceRefs",[]):
   if ref not in em: errs.append(f'{c.get("claimId")}: invalid evidence ref {ref}')
   elif c.get("supportLevel")=="full_text_supported" and em[ref][1].get("type")!="full_text": errs.append(f'{c.get("claimId")}: full text claim uses non-full-text evidence')
 for q in d.get("quantitativeResults",[]):
  if not q.get("evidenceRefs"): errs.append("quantitative result missing evidence")
 if any(x in c.get("text","").lower() for c in d.get("claims",[]) for x in ("major breakthrough","重大突破","首次证实")): errs.append("unsupported strong conclusion")
 return errs
def demo(pkg,outdir):
 outdir.mkdir(parents=True,exist_ok=True); picks=[]
 for s in ("Biology","Physics"):
  picks.extend([p for p in pkg.get("papers",[]) if p.get("subject")==s and p.get("abstract")][:1])
 for p in picks:
  doi=p["doi"]; refs=[f"{doi}#e{i}" for i,_ in enumerate(p.get("evidence",[]))]
  d={"schemaVersion":"1.0","kind":"science_editorial_draft","articleId":"science-"+re.sub(r"[^a-z0-9]+","-",doi.lower()).strip("-"),"editorialStatus":"Draft","category":"Science","topic":p.get("subject") or "Science","headline":"论文报告："+(p.get("title") or ""),"subheadline":"基于摘要和元数据，等待进一步原文核查。","publication":{"doi":doi,"title":p.get("title"),"journal":p.get("journal"),"publicationDate":p.get("publicationDate"),"publicationDatePrecision":"day" if len(str(p.get("publicationDate","")).split("-"))==3 else "unknown"},"lead":"该研究论文提出了具体研究问题；以下仅反映当前证据包可支持的范围。","researchQuestion":"论文摘要所述的研究问题是什么？","methods":"仅依据 Evidence package 中保存的摘要和元数据转述；未声称已阅读全文。","keyFindings":["论文摘要报告了方法和主要发现，具体表述仍需核对原文。"],"quantitativeResults":[],"limitations":["当前证据主要来自摘要和元数据，不能替代全文审查。","尚未核对补充材料、统计方法和系统误差。"],"broaderSignificance":"该结果可能为相关研究提供线索，但科学意义和适用范围需要结合全文判断。","sources":[{"doi":doi,"url":e["url"],"sourceType":e["type"]} for e in p.get("evidence",[]) if e.get("url")][:3],"claims":[{"claimId":"claim-1","text":"论文摘要报告了该研究的研究问题、方法和结果。","claimType":"sourced_fact","evidenceRefs":refs[:1],"supportLevel":"abstract_supported"}],"verificationWarnings":["草稿未完成独立科学事实核查。","不得将摘要支持内容改写为全文已验证结论。"]}
  (outdir/(d["articleId"]+".json")).write_text(json.dumps(d,ensure_ascii=False,indent=2)+"
")
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--evidence",required=True); ap.add_argument("--selection-output"); ap.add_argument("--draft-dir"); ap.add_argument("--review"); a=ap.parse_args(); pkg=load(a.evidence)
 if a.selection_output: Path(a.selection_output).parent.mkdir(parents=True,exist_ok=True); Path(a.selection_output).write_text(json.dumps(select(pkg),ensure_ascii=False,indent=2)+"
")
 if a.draft_dir: demo(pkg,Path(a.draft_dir))
 if a.review:
  e=review(load(a.review),pkg); print(json.dumps({"valid":not e,"errors":e},ensure_ascii=False)); return 0 if not e else 1
if __name__=="__main__": raise SystemExit(main() or 0)
