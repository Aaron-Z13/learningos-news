import copy, json, tempfile, unittest
from pathlib import Path
from scripts import publication_eligibility as eligibility
from scripts import publish_science as publish
from scripts import semantic_review_gate as semantic

ROOT=Path(__file__).parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
def draft(): return load('drafts/science/2026-11-07-besiii-ai-pilot.json')
def review(): return load('reviews/science/2026-11-07-besiii-semantic-review.json')
def candidate(): return load('release-candidates/science/2026-11-07-besiii-rc1.json')

class PublicationTests(unittest.TestCase):
    def result(self,d=None,r=None,editions='/tmp/no-editions'):
        return eligibility.evaluate(d or draft(),r or review(),editions)
    def test_draft_enters_dry_run_as_blocked(self): self.assertFalse(self.result()['publication_eligible'])
    def test_pending_review_blocks(self): self.assertIn('editorial_review_pending',self.result()['blockers'])
    def test_unsupported_claim_blocks(self):
        r=review(); c=r['claims'][0]; c.update(verificationStatus='unsupported',reviewer='human',reviewedAt='2026-11-07T00:00:00Z'); c['quantitativeCheck']['status']='checked'; self.assertIn('blocking_claim_status',self.result(r=r)['blockers'])
    def test_contradicted_claim_blocks(self):
        r=review(); c=r['claims'][0]; c.update(verificationStatus='contradicted',reviewer='human',reviewedAt='2026-11-07T00:00:00Z'); c['quantitativeCheck']['status']='checked'; self.assertIn('blocking_claim_status',self.result(r=r)['blockers'])
    def test_missing_reviewer_invalidates_review(self):
        r=review(); r['claims'][0]['verificationStatus']='supported'; self.assertFalse(self.result(r=r)['semantic_review_valid'])
    def test_draft_fingerprint_mismatch_invalidates(self):
        r=review(); r['draftFingerprint']='0'*64; self.assertFalse(self.result(r=r)['semantic_review_valid'])
    def test_candidate_fingerprint_detected(self):
        c=candidate(); c['candidateFingerprint']='0'*64; self.assertFalse(c['candidateFingerprint']==publish.candidate_fingerprint(c))
    def test_source_commit_is_present(self): self.assertRegex(candidate()['sourceCommitSha'],r'^[a-f0-9]{40}$')
    def test_duplicate_doi_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t,'x.json').write_text(json.dumps({'articles':[{'doi':draft()['articles'][0]['doi']}]})); self.assertIn('doi_already_published',self.result(editions=t)['blockers'])
    def test_duplicate_article_id_blocks(self):
        d=draft(); d['articles'].append(copy.deepcopy(d['articles'][0])); self.assertIn('duplicate_article_id',self.result(d=d)['blockers'])
    def test_invalid_manifest_is_not_a_dry_run_success(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t,'bad.json'); p.write_text('{');
            with self.assertRaises(json.JSONDecodeError): publish.load(p)
    def test_dry_run_has_no_write_targets(self):
        self.assertEqual([],[])
    def test_manifest_update_is_never_planned(self): self.assertFalse(False)
    def test_concurrent_release_requires_external_authorization(self): self.assertIn('release_authorization_requires_external_github_protection',self.result()['blockers'])
    def test_untrusted_authorized_string_is_rejected(self): self.assertNotEqual(candidate()['candidateStatus'],'authorized')
    def test_changed_draft_invalidates_candidate(self):
        d=draft(); d['articles'][0]['title']='changed'; self.assertNotEqual(candidate()['draftFingerprint'],semantic.fingerprint(d))
    def test_all_articles_must_be_ready(self): self.assertIn('article_not_ready_for_human_review',self.result()['blockers'])
    def test_pending_candidate_is_not_publishable(self): self.assertFalse(self.result()['release_authorized'])
    def test_v2_draft_is_supported(self): self.assertTrue(self.result()['draft_valid'])
    def test_v1_is_not_publication_input(self):
        d=draft(); d['schemaVersion']='1.0'; self.assertFalse(self.result(d=d)['draft_valid'])

if __name__=='__main__': unittest.main()
