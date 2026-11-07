#!/usr/bin/env python3
"""Fail-closed quality gate for LearningOS science editorial drafts."""
from __future__ import annotations
import argparse, json, re, sys, urllib.error, urllib.request
from datetime import date
from pathlib import Path

STATUSES={"Draft","Needs More Evidence","Ready","Published","Rejected"}
MAJOR_CLAIM=re.compile(r"(重大突破|首次证明|彻底解决|改变了?该领域|已证实治疗有效|证明了?生命起源)",re.I)

class GateError(Exception): pass

def norm(s):
    return re.sub(r"[^a-z0-9]+","",str(s or "").lower())

def load(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e: raise GateError(f"无法读取JSON: {path}: {e}")

def valid_date(v):
    try: date.fromisoformat(v); return True
    except Exception: return False

def verify_doi(article, timeout=20):
    v=article.get("doiVerification")
    if isinstance(v,dict) and v.get("verified") is True:
        required=("titleMatch","journalMatch","dateMatch")
        if all(v.get(k) is True for k in required): return {"method":"recorded","verified":True}
        raise GateError(f"{article['id']}: DOI核验记录存在冲突")
    doi=article["doi"]
    req=urllib.request.Request("https://api.crossref.org/works/"+doi,headers={"User-Agent":"LearningOS-News-Editorial-Gate/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: msg=json.load(r)["message"]
    except Exception as e:
        raise GateError(f"{article['id']}: DOI无法通过Crossref核验: {e}")
    title=norm((msg.get("title") or [""])[0])
    journal=norm(msg.get("container-title",[""])[0])
    if not title or norm(article["title"]) not in title and title not in norm(article["title"]):
        raise GateError(f"{article['id']}: DOI标题不匹配")
    if not journal or norm(article["journal"]) not in journal and journal not in norm(article["journal"]):
        raise GateError(f"{article['id']}: DOI期刊不匹配")
    return {"method":"crossref","verified":True}

def check_evidence(a):
    ev=a.get("evidence")
    if not isinstance(ev,list) or not ev: raise GateError(f"{a['id']}: 缺少证据记录")
    for e in ev:
        if not all(isinstance(e.get(k),str) and e[k].strip() for k in ("claim","sourceUrl","locator","evidenceType")):
            raise GateError(f"{a['id']}: 证据记录不完整")
    text=" ".join(str(x) for x in a.get("body",[]))
    if MAJOR_CLAIM.search(text) and not any(e.get("evidenceType") in {"full_text","publisher_abstract"} for e in ev):
        raise GateError(f"{a['id']}: 重大结论缺少正文或出版社证据")

def duplicates(a, editions_dir):
    if not editions_dir.exists(): return
    for p in editions_dir.rglob("*.json"):
        try: data=load(p)
        except GateError: continue
        for old in data.get("articles",[]):
            if str(old.get("doi","")).lower()==a["doi"].lower():
                raise GateError(f"{a['id']}: DOI已在正式Edition中出现: {p}")

def validate(draft, editions_dir):
    if draft.get("schemaVersion")!="1.0" or draft.get("kind")!="science_editorial_draft":
        raise GateError("Draft Schema版本或kind无效")
    if not valid_date(draft.get("date","")): raise GateError("Draft日期无效")
    arts=draft.get("articles")
    if not isinstance(arts,list) or not arts: raise GateError("没有文章")
    ids=set(); dois=set(); results=[]
    for a in arts:
        for k in ("id","status","doi","title","journal","paperPublicationDate","sources","evidence","body"):
            if k not in a: raise GateError(f"{a.get('id','unknown')}: 缺少字段 {k}")
        if a["status"]!="Ready": raise GateError(f"{a['id']}: 状态为 {a['status']}，禁止进入发布候选")
        if a["id"] in ids: raise GateError(f"重复文章ID: {a['id']}")
        if a["doi"].lower() in dois: raise GateError(f"重复DOI: {a['doi']}")
        if not valid_date(a["paperPublicationDate"]): raise GateError(f"{a['id']}: 发表日期无效")
        ids.add(a["id"]); dois.add(a["doi"].lower())
        check_evidence(a); duplicates(a,editions_dir); results.append({**verify_doi(a),"id":a["id"]})
    return {"status":"pass","articles":results,"count":len(results)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--draft",required=True); ap.add_argument("--editions-dir",default="editions"); ap.add_argument("--output",required=True)
    args=ap.parse_args()
    try:
        result=validate(load(args.draft),Path(args.editions-dir))
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False)); return 0
    except GateError as e:
        print("QUALITY_GATE_FAILED: "+str(e),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
