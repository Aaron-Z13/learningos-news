#!/usr/bin/env python3
"""Fail-closed quality gate for LearningOS science editorial drafts."""
from __future__ import annotations
import argparse, json, re, sys, urllib.error, urllib.request
from datetime import date
from pathlib import Path

STATUSES={"Draft","Needs More Evidence","Ready","Published","Rejected"}
EVIDENCE_TYPES={"publisher_abstract","preprint_abstract","full_text","supplementary_information","institutional_copy"}
JOURNAL_ALIASES={"physicalreviewletters":"physicalreviewletters","physrevlett":"physicalreviewletters","journalofamericanchemicalsociety":"journalofamericanchemicalsociety","jacs":"journalofamericanchemicalsociety","astronomyastrophysics":"astronomyastrophysics","aanda":"astronomyastrophysics"}

def canonical_journal(value):
    key=norm(value)
    return JOURNAL_ALIASES.get(key,key)
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

def check_schema_file(path):
    schema=load(path)
    if schema.get("title")!="LearningOS Science Editorial Draft":
        raise GateError("Draft Schema标题无效")
    required=set(schema.get("required",[]))
    if not {"schemaVersion","kind","draftId","date","articles"}.issubset(required):
        raise GateError("Draft Schema缺少顶层必填字段")
    items=schema.get("properties",{}).get("articles",{}).get("items",{})
    item_required=set(items.get("required",[]))
    needed={"id","status","doi","title","originalTitle","journal","authors","paperPublicationDate","sources","evidence","body"}
    if not needed.issubset(item_required):
        raise GateError("Draft Schema缺少文章必填字段")

def verify_doi(article, timeout=20):
    doi=article["doi"]
    req=urllib.request.Request("https://api.crossref.org/works/"+doi,headers={"User-Agent":"LearningOS-News-Editorial-Gate/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: msg=json.load(r)["message"]
    except Exception as e:
        raise GateError(f"{article['id']}: DOI无法通过Crossref核验: {e}")
    expected_title=norm(article.get("originalTitle") or article["title"])
    actual_title=norm((msg.get("title") or [""])[0])
    if not actual_title or actual_title != expected_title:
        raise GateError(f"{article['id']}: DOI标题不匹配")
    expected_journal=norm(article["journal"])
    actual_journal=norm((msg.get("container-title") or [""])[0])
    if not actual_journal or (expected_journal not in actual_journal and actual_journal not in expected_journal):
        raise GateError(f"{article['id']}: DOI期刊不匹配")
    authors=msg.get("author") or []
    expected_first=(article.get("authors") or [""])[0].split()[-1].lower()
    actual_first=str(authors[0].get("family","")).lower() if authors else ""
    if expected_first and actual_first and expected_first != actual_first:
        raise GateError(f"{article['id']}: DOI首作者不匹配")
    parts=((msg.get("published-online") or msg.get("published-print") or msg.get("published") or {}).get("date-parts") or [[]])[0]
    if parts and str(parts[0]) != article["paperPublicationDate"][:4]:
        raise GateError(f"{article['id']}: DOI发表年份不匹配")
    return {"method":"crossref","verified":True,"titleMatch":True,"authorsMatch":True,"journalMatch":True,"dateMatch":True}

def check_evidence(a):
    ev=a.get("evidence")
    if not isinstance(ev,list) or not ev: raise GateError(f"{a['id']}: 缺少证据记录")
    for e in ev:
        if not all(isinstance(e.get(k),str) and e[k].strip() for k in ("claim","sourceUrl","locator","evidenceType")):
            raise GateError(f"{a['id']}: 证据记录不完整")
        if e["evidenceType"] not in EVIDENCE_TYPES:
            raise GateError(f"{a['id']}: 未知证据类型 {e['evidenceType']}")
        if not e["sourceUrl"].startswith("https://"):
            raise GateError(f"{a['id']}: 证据来源必须是HTTPS")
    text=" ".join(str(x) for x in a.get("body",[]))
    if MAJOR_CLAIM.search(text) and not any(e.get("evidenceType") in {"full_text","publisher_abstract"} for e in ev):
        raise GateError(f"{a['id']}: 重大结论缺少正文或出版社证据")

def duplicates(a, editions_dir):
    if not editions_dir.exists(): return
    for p in editions_dir.rglob("*.json"):
        try: data=load(p)
        except GateError as exc: raise GateError(f"正式Edition无法解析: {p}: {exc}")
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
        for k in ("id","status","doi","title","originalTitle","journal","authors","paperPublicationDate","sources","evidence","body"):
            if k not in a: raise GateError(f"{a.get('id','unknown')}: 缺少字段 {k}")
        if a["status"]!="Ready": raise GateError(f"{a['id']}: 状态为 {a['status']}，禁止进入发布候选")
        if a["id"] in ids: raise GateError(f"重复文章ID: {a['id']}")
        if a["doi"].lower() in dois: raise GateError(f"重复DOI: {a['doi']}")
        if not valid_date(a["paperPublicationDate"]): raise GateError(f"{a['id']}: 发表日期无效")
        ids.add(a["id"]); dois.add(a["doi"].lower())
        check_evidence(a); duplicates(a,editions_dir); results.append({**verify_doi(a),"id":a["id"]})
    return {"status":"pass","articles":results,"count":len(results)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--draft",required=True); ap.add_argument("--editions-dir",default="editions"); ap.add_argument("--schema",default="schemas/science-editorial-draft.schema.json"); ap.add_argument("--output",required=True)
    args=ap.parse_args()
    try:
        check_schema_file(Path(args.schema))
        result=validate(load(args.draft),Path(args.editions_dir))
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False)); return 0
    except GateError as e:
        print("QUALITY_GATE_FAILED: "+str(e),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
