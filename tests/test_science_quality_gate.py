import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import science_quality_gate as gate


def article(**overrides):
    value = {
        "id": "a1", "status": "Ready", "doi": "10.1/x", "title": "A study",
        "journal": "Journal", "authors": ["Author"], "paperPublicationDate": "2026-11-07",
        "sources": [{"title": "source", "url": "https://example.com"}],
        "evidence": [{"claim": "measured value", "sourceUrl": "https://example.com",
                      "locator": "abstract", "evidenceType": "publisher_abstract"}],
        "doiVerification": {"verified": True, "titleMatch": True, "authorsMatch": True,
                            "journalMatch": True, "dateMatch": True},
        "body": ["研究问题", "方法和结果", "局限"],
    }
    value.update(overrides)
    return value


class QualityGateTests(unittest.TestCase):
    def draft(self, articles):
        return {"schemaVersion": "1.0", "kind": "science_editorial_draft",
                "draftId": "test", "date": "2026-11-07", "articles": articles}

    def test_valid_ready_article_passes(self):
        result = gate.validate(self.draft([article()]), Path("/tmp/no-editions"))
        self.assertEqual(result["status"], "pass")

    def test_error_doi_is_rejected(self):
        bad = article(doiVerification={"verified": True, "titleMatch": False,
                                       "authorsMatch": True, "journalMatch": True,
                                       "dateMatch": True})
        with self.assertRaises(gate.GateError):
            gate.validate(self.draft([bad]), Path("/tmp/no-editions"))

    def test_missing_evidence_is_rejected(self):
        with self.assertRaises(gate.GateError):
            gate.validate(self.draft([article(evidence=[])]), Path("/tmp/no-editions"))

    def test_duplicate_formal_publication_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "science.json"
            p.write_text(json.dumps({"articles": [{"doi": "10.1/x"}]}), encoding="utf-8")
            with self.assertRaises(gate.GateError):
                gate.validate(self.draft([article()]), Path(tmp))

    def test_unreviewed_status_is_rejected(self):
        with self.assertRaises(gate.GateError):
            gate.validate(self.draft([article(status="Needs More Evidence")]), Path("/tmp/no-editions"))


if __name__ == "__main__":
    unittest.main()
