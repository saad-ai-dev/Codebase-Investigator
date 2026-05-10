from __future__ import annotations

from models import AnswerPayload, Snippet, TurnRecord, VerifierReport
from openai_client import StructuredSchema

ANSWER_INSTRUCTIONS = """You are a codebase investigator.

Use only the supplied repository overview, prior-turn ledger, and evidence snippets.

Rules:
- Do not invent files, symbols, or line ranges.
- Cite snippets by snippet ID in square brackets, for example [S1] or [S1,S3].
- Distinguish observed behavior from risk assessment and recommendations.
- If the evidence is partial, say so directly.
- If you are changing an earlier conclusion, say which earlier claim you are correcting.
- Keep the answer concise but specific.
"""


AUDIT_INSTRUCTIONS = """You are an independent reviewer of a codebase investigation answer.

You did not produce the answer.

Review the answer for:
- unsupported claims
- misuse of cited snippets
- contradictions with the prior-turn ledger
- recommendations that may break behavior shown in the snippets
- overconfidence where evidence is incomplete

Do not rewrite the answer. Judge whether it is trustworthy and explain why.
"""


ANSWER_SCHEMA = StructuredSchema(
    name="investigator_answer",
    schema={
        "type": "object",
        "properties": {
            "answer_markdown": {"type": "string"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": ["observation", "risk", "recommendation", "uncertainty"],
                        },
                        "statement": {"type": "string"},
                        "snippet_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "supersedes_claim_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "claim_id",
                        "kind",
                        "statement",
                        "snippet_ids",
                        "supersedes_claim_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "open_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "needs_more_evidence": {"type": "boolean"},
        },
        "required": ["answer_markdown", "claims", "open_questions", "needs_more_evidence"],
        "additionalProperties": False,
    },
)


AUDIT_SCHEMA = StructuredSchema(
    name="investigator_audit",
    schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "warn", "fail"]},
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "claim_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "snippet_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["severity", "title", "detail", "claim_ids", "snippet_ids"],
                    "additionalProperties": False,
                },
            },
            "missing_checks": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["verdict", "summary", "findings", "missing_checks"],
        "additionalProperties": False,
    },
)


def build_answer_prompt(
    *,
    question: str,
    repository_overview: str,
    prior_turn_ledger: str,
    snippets: list[Snippet],
) -> str:
    snippet_blocks = "\n\n".join(snippet.to_prompt_block() for snippet in snippets)
    return (
        f"Question:\n{question}\n\n"
        f"Repository overview:\n{repository_overview}\n\n"
        f"Prior-turn ledger:\n{prior_turn_ledger}\n\n"
        f"Evidence snippets:\n{snippet_blocks}\n"
    )


def build_audit_prompt(
    *,
    question: str,
    prior_turn_ledger: str,
    rendered_answer: str,
    answer: AnswerPayload,
    verifier: VerifierReport,
    snippets: list[Snippet],
) -> str:
    claims = (
        "\n".join(
            f"- {claim.claim_id} ({claim.kind}): {claim.statement} | snippets={claim.snippet_ids}"
            for claim in answer.claims
        )
        or "(none)"
    )
    verifier_lines = (
        "\n".join(f"- {issue.severity.upper()}: {issue.message}" for issue in verifier.issues)
        or "- No verifier issues."
    )
    snippet_blocks = "\n\n".join(snippet.to_prompt_block() for snippet in snippets)
    return (
        f"Question:\n{question}\n\n"
        f"Prior-turn ledger:\n{prior_turn_ledger}\n\n"
        f"Rendered answer:\n{rendered_answer}\n\n"
        f"Structured claims:\n{claims}\n\n"
        f"Verifier verdict: {verifier.verdict}\n"
        f"Verifier details:\n{verifier_lines}\n\n"
        f"Cited evidence bundle:\n{snippet_blocks}\n"
    )


def build_prior_turn_ledger(turns: list[TurnRecord], max_turns: int = 6) -> str:
    if not turns:
        return "No prior turns."

    selected = turns[-max_turns:]
    blocks = []
    for turn in selected:
        claims = []
        for claim in turn.answer.claims[:6]:
            citation_labels = [
                snippet.label()
                for snippet in turn.snippets
                if snippet.snippet_id in claim.snippet_ids
            ]
            claim_line = f"{claim.claim_id} ({claim.kind}): {claim.statement}"
            if citation_labels:
                claim_line += f" [{'; '.join(citation_labels)}]"
            claims.append(claim_line)
        blocks.append(
            f"Turn {turn.turn_number}\n"
            f"Question: {turn.question}\n"
            f"Key claims:\n"
            f"{chr(10).join(f'- {claim}' for claim in claims) if claims else '- None'}"
        )
    return "\n\n".join(blocks)
