import copy, hashlib, json, tempfile, unittest
from pathlib import Path
from scripts import semantic_review_gate as gate

def draft():
    return {"schemaVersion":"2.0","kind":"science_editorial_draft","draftId":"d1","date":"2026-11-07","articles":[{"id":"a1","status":"Draft","doi":"10.1/x","title":"T","originalTitle":"T","journal":"J","authors":["A"],"paperPublicationDate":"2026-11-07","sources":[{"url":"https://x"}],"evidence":[{"evidenceId":"e1","claimId":"c1","sourceDoi":"10.1/x","sourceUrl":"https://x","locator":"abstract paragraph 1","checkedContent":"abstract","evidenceType":"metadata_abstract"}],"claims":[{"claimId":"c1","text":"value","claimType":"quantitative","evidenceRefs":["e1"],"editorialFactCheck":"not_performed_by_automated_gate"}],"body":["q","m","l"]}]}

def review(d=None):
    d=d or draft(); fp=gate.fingerprint(d)
    return {"schemaVersion":"1.0","kind":"science_semantic_review","draftId":"d1","draftFingerprint":fp,"reviewStatus":"pending_review","claims":[{"claimId":"c1","claimText":"value","evidenceRefs":["e1"],"evidenceSource":["https://x"],"verificationMethod":"human review required","verificationStatus":"unreviewed","verificationNotes":"not reviewed","reviewer":None,"reviewedAt":None,"claimType":"quantitative","quantitativeCheck":{"status":"not_performed","notes":"not performed"}}],"evidenceCoverage":[{"evidenceId":"e1","level":"L1","evidenceType":"metadata_abstract","accessStatus":"accessible","checkedScope":"abstract only","locator":"paragraph 1","notes":"L1"}],"review":{"reviewerId":None,"decision":"pending_review","reviewTimestamp":None,"reviewNotes":"pending","claimVerificationSummary":"unreviewed","evidenceCoverageSummary":"L1"}}

class SemanticReviewTests(unittest.TestCase):
    def assertFails(self,r,d=None):
        with self.assertRaises(gate.ReviewError): gate.validate(d or draft(),r)
    def test_normal_claim_evidence_is_pending_not_approved(self):
        result=gate.validate(draft(),review()); self.assertTrue(result["draft_valid"]); self.assertFalse(result["publication_eligible"])
    def test_missing_evidence_reference_fails(self):
        r=review(); r["claims"][0]["evidenceRefs"]=["missing"]; self.assertFails(r)
    def test_same_doi_unsupported_claim_is_not_supported(self):
        r=review(); r["claims"][0]["verificationStatus"]="unsupported"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; r["claims"][0]["quantitativeCheck"]["status"]="checked"; self.assertTrue(gate.validate(draft(),r)["publication_eligible"] is False)
    def test_numeric_unit_or_condition_requires_human_check(self):
        r=review(); r["claims"][0]["verificationStatus"]="supported"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; r["claims"][0]["quantitativeCheck"]={"status":"not_performed","notes":"unit differs"}; self.assertFails(r)
    def test_statistical_systematic_confusion_not_approved(self):
        r=review(); r["claims"][0]["verificationStatus"]="supported"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; r["claims"][0]["quantitativeCheck"]={"status":"not_performed","notes":"stat/systematic distinction unresolved"}; self.assertFails(r)
    def test_abstract_cannot_be_l2(self):
        r=review(); r["evidenceCoverage"][0]["level"]="L2"; self.assertFails(r)
    def test_l2_requires_locator_and_scope(self):
        r=review(); r["evidenceCoverage"][0]["level"]="L2"; r["evidenceCoverage"][0]["checkedScope"]=""; self.assertFails(r)
    def test_unreviewed_is_valid_but_not_approved(self):
        self.assertEqual(gate.validate(draft(),review())["reviewStatus"],"pending_review")
    def test_unsupported_blocks_approval(self):
        r=review(); r["reviewStatus"]=r["review"]["decision"]="approved"; r["review"]["reviewerId"]="human"; r["review"]["reviewTimestamp"]="2026-11-07T00:00:00Z"; r["claims"][0]["verificationStatus"]="unsupported"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; self.assertFails(r)
    def test_contradicted_blocks_approval(self):
        r=review(); r["reviewStatus"]=r["review"]["decision"]="approved"; r["review"]["reviewerId"]="human"; r["review"]["reviewTimestamp"]="2026-11-07T00:00:00Z"; r["claims"][0]["verificationStatus"]="contradicted"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; self.assertFails(r)
    def test_approved_requires_reviewer(self):
        r=review(); r["reviewStatus"]=r["review"]["decision"]="approved"; self.assertFails(r)
    def test_invalid_review_state_fails(self):
        r=review(); r["reviewStatus"]=r["review"]["decision"]="bogus"; self.assertFails(r)
    def test_missing_claim_reviewer_fails_when_supported(self):
        r=review(); r["claims"][0]["verificationStatus"]="supported"; self.assertFails(r)
    def test_modified_draft_invalidates_old_approval(self):
        d=draft(); r=review(d); d["articles"][0]["title"]="changed"; self.assertFails(r,d)
    def test_automatic_string_similarity_cannot_support(self):
        r=review(); r["claims"][0]["verificationStatus"]="supported"; r["claims"][0]["reviewer"]="human"; r["claims"][0]["reviewedAt"]="2026-11-07T00:00:00Z"; r["claims"][0]["verificationMethod"]="string_similarity"; self.assertFails(r)
    def test_missing_claim_coverage_fails(self):
        r=review(); r["claims"]=[]; self.assertFails(r)

if __name__=="__main__": unittest.main()
