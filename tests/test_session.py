import tempfile
import unittest
from pathlib import Path

from github import GitHubRepoRef
from models import (
    AnswerPayload,
    AuditReport,
    Claim,
    Snippet,
    TurnRecord,
    VerifierReport,
)
from session import InvestigationSession, SessionStore


class SessionPersistenceTest(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "session"
            repo_dir = session_dir / "repo"
            repo_dir.mkdir(parents=True)

            session = InvestigationSession(
                session_dir=session_dir,
                repo_ref=GitHubRepoRef(
                    owner="owner",
                    repo="repo",
                    original_url="https://github.com/owner/repo",
                ),
                repo_dir=repo_dir,
                created_at="2026-05-10T00:00:00+00:00",
            )
            turn = TurnRecord(
                turn_number=1,
                timestamp="2026-05-10T00:01:00+00:00",
                question="How does auth work?",
                snippets=[
                    Snippet(
                        snippet_id="S1",
                        path="src/auth.py",
                        start_line=1,
                        end_line=5,
                        text="def login():\n    pass",
                        reason="matched terms: auth",
                        score=1.0,
                    )
                ],
                answer=AnswerPayload(
                    answer_markdown="It logs in [S1].",
                    claims=[
                        Claim(
                            claim_id="c1",
                            kind="observation",
                            statement="It logs in.",
                            snippet_ids=["S1"],
                        )
                    ],
                ),
                rendered_answer="It logs in [src/auth.py:1-5].",
                verifier=VerifierReport(
                    verdict="pass",
                    issues=[],
                    cited_snippet_ids=["S1"],
                    unknown_snippet_ids=[],
                    uncited_claim_ids=[],
                ),
                audit=AuditReport(
                    verdict="pass",
                    summary="Looks grounded.",
                ),
            )
            session.append_turn(turn)
            session.save()

            loaded = SessionStore(Path(tmpdir)).load(session_dir)

            self.assertEqual(len(loaded.turns), 1)
            self.assertEqual(loaded.turns[0].question, "How does auth work?")
            self.assertEqual(loaded.turns[0].snippets[0].path, "src/auth.py")


if __name__ == "__main__":
    unittest.main()
