import tempfile
import unittest
from pathlib import Path

from github import GitHubRepoRef
from models import (
    AnswerPayload,
    AuditFinding,
    AuditReport,
    Claim,
    Snippet,
    TurnRecord,
    VerifierIssue,
    VerifierReport,
)
from session import InvestigationSession, SessionStore
from webapp import serialize_session, serialize_turn


class WebAppSerializationTest(unittest.TestCase):
    def test_serialize_turn_contains_frontend_fields(self) -> None:
        turn = TurnRecord(
            turn_number=2,
            timestamp="2026-05-10T00:02:00+00:00",
            question="Why is this async?",
            snippets=[
                Snippet(
                    snippet_id="S1",
                    path="src/service.py",
                    start_line=10,
                    end_line=18,
                    text="async def run():\n    return 1",
                    reason="symbol definition for run",
                    score=4.0,
                )
            ],
            answer=AnswerPayload(
                answer_markdown="It is async [S1].",
                claims=[
                    Claim(
                        claim_id="c1",
                        kind="observation",
                        statement="It is async.",
                        snippet_ids=["S1"],
                    )
                ],
                open_questions=["Does anything await it?"],
                needs_more_evidence=True,
            ),
            rendered_answer="It is async [src/service.py:10-18].",
            verifier=VerifierReport(
                verdict="warn",
                issues=[VerifierIssue(severity="medium", message="Needs deeper evidence.")],
                cited_snippet_ids=["S1"],
                unknown_snippet_ids=[],
                uncited_claim_ids=[],
            ),
            audit=AuditReport(
                verdict="warn",
                summary="Mostly grounded.",
                findings=[
                    AuditFinding(
                        severity="medium",
                        title="Partial evidence",
                        detail="The snippet does not show the caller.",
                    )
                ],
            ),
        )

        payload = serialize_turn(turn)

        self.assertEqual(payload["turn_number"], 2)
        self.assertEqual(payload["snippets"][0]["label"], "src/service.py:10-18")
        self.assertEqual(payload["answer"]["claims"][0]["claim_id"], "c1")
        self.assertEqual(payload["audit"]["findings"][0]["title"], "Partial evidence")

    def test_serialize_session_can_include_turns(self) -> None:
        session = InvestigationSession(
            session_dir=Path("/tmp/example-session"),
            repo_ref=GitHubRepoRef(
                owner="openai",
                repo="openai-python",
                original_url="https://github.com/openai/openai-python",
            ),
            repo_dir=Path("/tmp/example-session/repo"),
            created_at="2026-05-10T00:00:00+00:00",
            turns=[],
        )

        payload = serialize_session(session, include_turns=True)

        self.assertEqual(payload["session_id"], "example-session")
        self.assertEqual(payload["repo"]["owner"], "openai")
        self.assertEqual(payload["turns"], [])


class SessionStoreLoadByIdTest(unittest.TestCase):
    def test_load_by_id_rejects_invalid_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(Path(tmpdir))
            with self.assertRaises(ValueError):
                store.load_by_id("../escape")


if __name__ == "__main__":
    unittest.main()
