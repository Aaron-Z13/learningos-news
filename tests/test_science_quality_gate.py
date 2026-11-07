import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import science_quality_gate as gate

def article(**overrides):
    value={"id":"a1","status":"Draft","previousStatus":None,"doi":"10.1/x","title":"中文标题","originalTitle":"A study","journal":"Journal","authors":["Author One"],"paperPublicationDate":"2026-11-07","sources":[{"title":"source","url":"https://example.com"}],"evidence":[{"evidenceId":"e1","claimId":"c1","claim":"measured value","sourceDoi":"10.1/x","sourceUrl":"https://example.com","locator":"publisher HTML, Results paragraph 1","checkedContent":"The measured value was 2.0 in the reported sample.","evidenceType":"full_text","verificationStatus":"verified","verificationRecord":{"checkedAt":"2026-11-07T00:00:00Z","method":"manual source reading","recordedBy":"editor"},"quantitativeSupport":True}],"claims":[{"claimId":"c1","text":"measured value","claimType":"quantitative","evidenceRefs":["e1"],"editorialFactCheck":"not_performed_by_automated_gate"}],"body":["研究问题","方法和结果","局限"]}
    value.update(overrides); return value

def crossref_message(**overrides):
    value={"title":["A study"],"container-title":["Journal"],"author":[{"family":"One","given":"Author"}],"published-online":{"date-parts":[[2026,11,7]]}}
    value.update(overrides); return value

class FakeResponse:
    def __init__(self,payload): self.payload=json.dumps({"message":payload}).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return self.payload

class QualityGateTests(unittest.TestCase):
    def draft(self,articles): return {"schemaVersion":"2.0","kind":"science_editorial_draft","draftId":"test","date":"2026-11-07","articles":articles}

    @patch.object(gate.urllib.request,"urlopen")
    def test_valid_draft_passes_with_mocked_crossref(self,m):
        m.return_value=FakeResponse(crossref_message()); result=gate.validate(self.draft([article()]),Path("/tmp/no-editions")); self.assertEqual(result["status"],"pass"); self.assertEqual(result["semanticFactCheck"],"not_performed_by_automated_gate")

    @patch.object(gate.urllib.request,"urlopen")
    def test_error_doi_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message(title=["Wrong"]))
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article()]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_title_author_journal_and_year_mismatch_are_rejected(self,m):
        for change in [{"title":["Wrong"]},{"author":[{"family":"Different"}]},{"container-title":["Other Journal"]},{"published-online":{"date-parts":[[2025,11,7]]}}]:
            with self.subTest(change=change):
                m.return_value=FakeResponse(crossref_message(**change))
                with self.assertRaises(gate.GateError): gate.validate(self.draft([article()]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_missing_evidence_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(evidence=[])]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_unknown_evidence_type_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        bad=[{"claim":"x","sourceUrl":"https://x","locator":"abstract","evidenceType":"guess"}]
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(evidence=bad)]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_duplicate_formal_publication_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,"science.json").write_text(json.dumps({"articles":[{"doi":"10.1/x"}]}),encoding="utf-8")
            with self.assertRaises(gate.GateError): gate.validate(self.draft([article()]),Path(tmp))

    @patch.object(gate.urllib.request,"urlopen")
    def test_journal_substring_counterexample_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message(**{"container-title":["Other Journal"]}))
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article()]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_unreviewed_status_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(status="Reviewed")]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_cross_paper_evidence_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(evidence=[{**article()["evidence"][0],"sourceDoi":"10.2/other"}])]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_full_text_url_without_checked_content_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(evidence=[{**article()["evidence"][0],"checkedContent":""}])]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_quantitative_claim_must_map_to_quantitative_evidence(self,m):
        m.return_value=FakeResponse(crossref_message())
        e={**article()["evidence"][0],"quantitativeSupport":False}
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(evidence=[e])]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_invalid_transition_is_rejected(self,m):
        m.return_value=FakeResponse(crossref_message())
        with self.assertRaises(gate.GateError): gate.validate(self.draft([article(status="ApprovedForHumanReview", previousStatus="Draft")]),Path("/tmp/no-editions"))

    @patch.object(gate.urllib.request,"urlopen")
    def test_malformed_formal_edition_fails_closed(self,m):
        m.return_value=FakeResponse(crossref_message())
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,"broken.json").write_text("{not-json",encoding="utf-8")
            with self.assertRaises(gate.GateError): gate.validate(self.draft([article()]),Path(tmp))

if __name__=="__main__": unittest.main()
