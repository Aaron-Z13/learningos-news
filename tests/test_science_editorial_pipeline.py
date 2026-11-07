import unittest
from unittest.mock import patch
from scripts.science_editorial_pipeline import select,review
def pkg(): return {"source":{"collectionDate":"2026-11-07"},"papers":[{"doi":"10.1/a","title":"A","journal":"J","subject":"Biology","publicationDate":"2026-11-01","abstract":"x","verifiedFields":{"doi":True},"fullTextAvailable":False,"evidence":[{"type":"publisher_abstract","url":"https://doi.org/10.1/a","locator":"abstract","retrievedAt":"x","version":"v"}]}]}
def draft(**kw):
 d={"schemaVersion":"1.0","kind":"science_editorial_draft","articleId":"science-a","editorialStatus":"Draft","category":"Science","topic":"Biology","headline":"标题","subheadline":"副标题","publication":{"doi":"10.1/a","title":"A","journal":"J","publicationDate":"2026-11-01"},"lead":"lead","researchQuestion":"q","methods":"m","keyFindings":["f"],"quantitativeResults":[],"limitations":["l"],"broaderSignificance":"谨慎解释","sources":[{"doi":"10.1/a","url":"https://doi.org/10.1/a","sourceType":"publisher_abstract"}],"claims":[{"claimId":"c1","text":"摘要报告","claimType":"sourced_fact","evidenceRefs":["10.1/a#e0"],"supportLevel":"abstract_supported"}],"verificationWarnings":[]}; d.update(kw); return d
class T(unittest.TestCase):
 def test_duplicate_selection(self): self.assertEqual(len({x["doi"] for x in select(pkg())["selected"]}),1)
 def test_missing_doi_fails(self): self.assertTrue(review(draft(publication={"doi":"10.1/m","title":"A","journal":"J","publicationDate":"2026"}),pkg()))
 def test_missing_claim_evidence_fails(self): self.assertTrue(review(draft(claims=[{"claimId":"c","text":"x","claimType":"sourced_fact","evidenceRefs":[],"supportLevel":"abstract_supported"}]),pkg()))
 def test_bad_reference_fails(self): self.assertTrue(review(draft(claims=[{"claimId":"c","text":"x","claimType":"sourced_fact","evidenceRefs":["10.1/a#e9"],"supportLevel":"abstract_supported"}]),pkg()))
 def test_abstract_not_full_text(self): self.assertTrue(review(draft(claims=[{"claimId":"c","text":"full","claimType":"sourced_fact","evidenceRefs":["10.1/a#e0"],"supportLevel":"full_text_supported"}]),pkg()))
 def test_strong_claim_fails(self): self.assertTrue(review(draft(claims=[{"claimId":"c","text":"重大突破","claimType":"interpretation","evidenceRefs":["10.1/a#e0"],"supportLevel":"abstract_supported"}]),pkg()))
 def test_invalid_status_fails(self): self.assertTrue(review(draft(editorialStatus="Approved"),pkg()))
 def test_no_candidates(self): self.assertEqual(select({"papers":[]})["selected"],[])
if __name__=="__main__": unittest.main()
