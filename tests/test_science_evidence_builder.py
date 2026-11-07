import unittest
from unittest.mock import patch
import scripts.science_evidence_builder as b
L={"kind":"science_editorial_input_index","date":"2026-11-07","runId":10,"runAttempt":1,"shortlistCount":1,"path":"x.json"}
H={"sourceRun":{"runId":10,"runAttempt":1,"collectorRunId":10,"collectorRunAttempt":1},"collection":{"date":"2026-11-07","status":"complete"},"shortlisting":{"selectedCount":1},"papers":[{"doi":"10.1234/test","title":"A Study","titleOriginal":"A Study","journal":"Journal","subject":"Physics","publicationDate":"2026-11-01"}]}
class T(unittest.TestCase):
 def test_consistency(self):
  x=dict(L);x["runId"]=11
  with self.assertRaises(ValueError):b.build(x,H)
 def test_dedup(self):
  cr={"DOI":"10.1234/test","title":["A Study"],"container-title":["Journal"],"author":[],"published":{"date-parts":[[2026,11,1]]},"URL":"https://doi.org/10.1234/test"}
  with patch.object(b,"crossref_record",return_value=cr),patch.object(b,"openalex_record",return_value=None):
   h=dict(H);h["papers"]=H["papers"]*2;self.assertEqual(len(b.build(L,h)["papers"]),1)
 def test_reject_mismatch(self):
  cr={"DOI":"10.1234/test","title":["Other"],"container-title":["Other Journal"],"author":[],"published":{"date-parts":[[2025]]}}
  with patch.object(b,"crossref_record",return_value=cr),patch.object(b,"openalex_record",return_value=None):
   self.assertEqual(b.build(L,H)["papers"][0]["editorialStatus"],"unverified")
 def test_abstract_not_fulltext(self):
  cr={"DOI":"10.1234/test","title":["A Study"],"container-title":["Journal"],"author":[],"published":{"date-parts":[[2026,11,1]]},"URL":"https://doi.org/10.1234/test"}
  with patch.object(b,"crossref_record",return_value=cr),patch.object(b,"openalex_record",return_value={"abstract_inverted_index":{"A":[0],"study":[1]},"locations":[]}):
   p=b.build(L,H)["papers"][0];self.assertEqual(p["abstract"],"A study");self.assertFalse(p["fullTextAvailable"])
if __name__=="__main__":unittest.main()
