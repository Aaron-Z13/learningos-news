#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import quote
from urllib.request import Request,urlopen
MAX_PAPERS=30; TIMEOUT=20; RETRIES=2
class EvidenceError(Exception): pass
def now_iso(): return datetime.now(timezone.utc).isoformat()
def fetch_json(url,retries=RETRIES):
    last="request failed"
    for i in range(retries+1):
        try:
            req=Request(url,headers={"Accept":"application/json","User-Agent":"LearningOS-Science-Evidence-Builder/1.0"})
            with urlopen(req,timeout=TIMEOUT) as r:
                if r.status!=200: raise EvidenceError(f"HTTP {r.status}")
                return json.loads(r.read().decode())
        except (HTTPError,URLError,TimeoutError,json.JSONDecodeError,EvidenceError) as e:
            last=str(e)
            if i<retries: time.sleep(.5*(2**i))
    raise EvidenceError(last)
def norm_doi(v): return re.sub(r"^https?://(dx\.)?doi\.org/","",(v or "").strip(),flags=re.I).lower()
def title_key(v): return re.sub(r"[^a-z0-9]+"," ",(v or "").lower()).strip()
def date_value(r):
    for k in ("published-online","published-print","issued","published"):
        p=r.get(k,{}).get("date-parts",[[]])[0]
        if p:return "-".join(str(x).zfill(2) for x in p)
    return None
def crossref_record(doi):
    d=fetch_json("https://api.crossref.org/works/"+quote(doi,safe=""))
    if not isinstance(d.get("message"),dict):raise EvidenceError("Crossref response missing message")
    return d["message"]
def verify_crossref(p):
    doi=norm_doi(p.get("doi"))
    if not doi:return None,["missing DOI"]
    try:r=crossref_record(doi)
    except EvidenceError as e:return None,[f"Crossref unavailable: {e}"]
    errs=[]; actual=norm_doi(r.get("DOI"))
    if actual!=doi:errs.append("DOI mismatch")
    if p.get("title") and title_key((r.get("title") or [""])[0])!=title_key(p.get("title")):errs.append("title mismatch")
    if p.get("journal") and (r.get("container-title") or [""])[0].casefold()!=p["journal"].casefold():errs.append("journal mismatch")
    if p.get("publicationDate") and date_value(r) and date_value(r)[:4]!=str(p["publicationDate"])[:4]:errs.append("publication year mismatch")
    authors=[{"given":a.get("given"),"family":a.get("family")} for a in r.get("author",[])[:20]]
    return {"doi":actual,"title":(r.get("title") or [""])[0],"journal":(r.get("container-title") or [""])[0],"authors":authors,"date":date_value(r),"url":r.get("URL")},errs
def openalex_record(doi):
    try:return fetch_json("https://api.openalex.org/works/https://doi.org/"+quote(doi,safe=":/"))
    except EvidenceError:return None
def restore_abstract(idx): return " ".join(w for _,w in sorted((pos,w) for w,poses in idx.items() for pos in poses))
def evidence_for_paper(p):
    doi=norm_doi(p.get("doi")); cr,errs=verify_crossref(p); ev=[]; abstract=None; source=None; full=False
    if cr and cr.get("url"):ev.append({"type":"publisher_abstract","url":cr["url"],"locator":"publisher DOI landing page","retrievedAt":now_iso(),"version":"published_record"})
    oa=openalex_record(doi) if doi else None
    if oa:
        idx=oa.get("abstract_inverted_index") or {}
        if idx:
            abstract=restore_abstract(idx); source="OpenAlex abstract_inverted_index"; ev.append({"type":"publisher_abstract","url":oa.get("id","https://openalex.org"),"locator":"OpenAlex abstract_inverted_index (reconstructed)","retrievedAt":now_iso(),"version":"metadata"})
        for loc in oa.get("locations") or []:
            u=loc.get("landing_page_url") or loc.get("pdf_url")
            if u and loc.get("is_oa"): full=True; ev.append({"type":"full_text","url":u,"locator":"OpenAlex OA location; content not fully validated","retrievedAt":now_iso(),"version":"open_access_location"}); break
    if abstract is None and p.get("subject")=="Biology":
        try:
            q=fetch_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&query=DOI:"+quote(doi,safe="")); rows=q.get("resultList",{}).get("result") or []
            if rows and rows[0].get("abstractText"):
                abstract=rows[0]["abstractText"]; source="Europe PMC abstract"; ev.append({"type":"publisher_abstract","url":"https://europepmc.org","locator":"Europe PMC abstractText","retrievedAt":now_iso(),"version":"metadata"})
        except EvidenceError: pass
    verified={"doi":bool(cr and not errs),"title":bool(cr and "title mismatch" not in errs),"journal":bool(cr and "journal mismatch" not in errs),"publicationYear":bool(cr and "publication year mismatch" not in errs)}
    return {"doi":doi,"originalTitle":p.get("titleOriginal") or p.get("title"),"title":p.get("title"),"journal":p.get("journal"),"subject":p.get("subject"),"authors":(cr or {}).get("authors",[]),"publicationDate":p.get("publicationDate"),"publicationDatePrecision":"day" if len(str(p.get("publicationDate","")).split("-"))==3 else "month_or_year","abstract":abstract,"abstractSource":source,"fullTextAvailable":full,"evidence":ev,"verifiedFields":verified,"verificationErrors":errs,"limitations":["Not a substitute for full-text scientific review.","Third-party abstracts are for editorial review, not republication."],"editorialStatus":"ready_for_editor" if verified["doi"] and not errs else "unverified"}
def build(latest,hist):
    src=hist.get("sourceRun") or {}; checks={"runId":latest.get("runId")==src.get("runId")==src.get("collectorRunId"),"runAttempt":latest.get("runAttempt")==src.get("runAttempt")==src.get("collectorRunAttempt"),"date":latest.get("date")==hist.get("collection",{}).get("date"),"status":hist.get("collection",{}).get("status")=="complete","count":latest.get("shortlistCount")==hist.get("shortlisting",{}).get("selectedCount")}
    if not all(checks.values()):raise ValueError("editorial input consistency check failed: "+json.dumps(checks))
    seen=set(); papers=[]
    for p in (hist.get("papers") or [])[:MAX_PAPERS]:
        d=norm_doi(p.get("doi"))
        if not d or d in seen:continue
        seen.add(d); papers.append(evidence_for_paper(p))
    return {"schemaVersion":"1.0","kind":"science_evidence_package","generatedAt":now_iso(),"source":{"latestIndex":latest,"historicalPath":latest.get("path"),"runId":latest.get("runId"),"runAttempt":latest.get("runAttempt"),"collectionDate":latest.get("date")},"limits":{"maxPapers":MAX_PAPERS,"processed":len(papers),"modelsUsed":[],"paidApisUsed":False},"papers":papers,"statistics":{"doiVerified":sum(x["verifiedFields"]["doi"] for x in papers),"abstractAvailable":sum(bool(x["abstract"]) for x in papers),"fullTextAvailable":sum(x["fullTextAvailable"] for x in papers),"unverified":sum(x["editorialStatus"]=="unverified" for x in papers)}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--latest",required=True); ap.add_argument("--historical"); ap.add_argument("--output",required=True); a=ap.parse_args()
    def load(x):return fetch_json(x) if x.startswith("http") else json.loads(Path(x).read_text())
    latest=load(a.latest); hp=a.historical or latest.get("path")
    if not hp:raise ValueError("latest index has no historical path")
    if not hp.startswith("http") and a.latest.startswith("http"):hp=a.latest.rsplit("/",1)[0]+"/"+hp.rsplit("/",1)[-1]
    out=build(latest,load(hp)); Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n"); print(json.dumps(out["statistics"]))
if __name__=="__main__":main()
