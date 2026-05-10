import unittest

from audit import verify_answer
from models import AnswerPayload, Claim, Snippet


class VerifyAnswerTest(unittest.TestCase):
    def test_passes_when_snippets_are_known(self) -> None:
        answer = AnswerPayload(
            answer_markdown="Auth is created in the handler [S1].",
            claims=[
                Claim(
                    claim_id="c1",
                    kind="observation",
                    statement="Auth is created in the handler.",
                    snippet_ids=["S1"],
                )
            ],
        )
        snippets = [
            Snippet(
                snippet_id="S1",
                path="src/auth.py",
                start_line=10,
                end_line=20,
                text="def login():\n    pass",
                reason="matched terms: login",
                score=1.0,
            )
        ]

        report = verify_answer(answer, snippets)

        self.assertEqual(report.verdict, "pass")
        self.assertEqual(report.unknown_snippet_ids, [])
        self.assertEqual(report.uncited_claim_ids, [])

    def test_fails_on_unknown_snippet(self) -> None:
        answer = AnswerPayload(
            answer_markdown="This is cited [S9].",
            claims=[
                Claim(
                    claim_id="c1",
                    kind="observation",
                    statement="Something happened.",
                    snippet_ids=["S9"],
                )
            ],
        )

        report = verify_answer(answer, [])

        self.assertEqual(report.verdict, "fail")
        self.assertIn("S9", report.unknown_snippet_ids)

    def test_warns_on_uncited_claim(self) -> None:
        answer = AnswerPayload(
            answer_markdown="There may be a risk.",
            claims=[
                Claim(
                    claim_id="c1",
                    kind="risk",
                    statement="There may be a risk.",
                    snippet_ids=[],
                )
            ],
        )

        report = verify_answer(answer, [])

        self.assertEqual(report.verdict, "warn")
        self.assertEqual(report.uncited_claim_ids, ["c1"])


if __name__ == "__main__":
    unittest.main()
