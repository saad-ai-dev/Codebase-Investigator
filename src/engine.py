from __future__ import annotations

import re
from datetime import datetime, timezone

from audit import empty_audit_from_verifier, verify_answer
from models import AnswerPayload, AuditFinding, AuditReport, Claim, Snippet, TurnRecord
from openai_client import OpenAIResponsesClient
from prompts import (
    ANSWER_INSTRUCTIONS,
    ANSWER_SCHEMA,
    AUDIT_INSTRUCTIONS,
    AUDIT_SCHEMA,
    build_answer_prompt,
    build_audit_prompt,
    build_prior_turn_ledger,
)
from repository import RepositorySnapshot
from session import InvestigationSession


class CodebaseInvestigator:
    def __init__(
        self,
        client: OpenAIResponsesClient,
        model: str = "gpt-5.5",
        audit_model: str = "gpt-5.4-mini",
        max_snippets: int = 12,
    ) -> None:
        self.client = client
        self.model = model
        self.audit_model = audit_model
        self.max_snippets = max_snippets

    def ask(self, session: InvestigationSession, question: str) -> TurnRecord:
        snapshot = RepositorySnapshot(session.repo_dir)
        prior_turn_ledger = build_prior_turn_ledger(session.turns)
        preferred_paths = self._preferred_paths(session, question)
        snippets = snapshot.search(
            question, preferred_paths=preferred_paths, max_snippets=self.max_snippets
        )

        answer_payload = self._generate_answer(
            question=question,
            repository_overview=snapshot.overview(),
            prior_turn_ledger=prior_turn_ledger,
            snippets=snippets,
        )
        verifier = verify_answer(answer_payload, snippets)
        rendered_answer = render_answer(answer_payload.answer_markdown, snippets)

        if verifier.verdict == "fail":
            audit = empty_audit_from_verifier(verifier)
        else:
            audit = self._generate_audit(
                question=question,
                prior_turn_ledger=prior_turn_ledger,
                rendered_answer=rendered_answer,
                answer=answer_payload,
                verifier=verifier,
                snippets=snippets,
            )

        turn = TurnRecord(
            turn_number=len(session.turns) + 1,
            timestamp=_utc_now(),
            question=question,
            snippets=snippets,
            answer=answer_payload,
            rendered_answer=rendered_answer,
            verifier=verifier,
            audit=audit,
        )
        session.append_turn(turn)
        session.save()
        return turn

    def _generate_answer(
        self,
        *,
        question: str,
        repository_overview: str,
        prior_turn_ledger: str,
        snippets: list[Snippet],
    ) -> AnswerPayload:
        raw = self.client.create_structured_output(
            model=self.model,
            instructions=ANSWER_INSTRUCTIONS,
            user_content=build_answer_prompt(
                question=question,
                repository_overview=repository_overview,
                prior_turn_ledger=prior_turn_ledger,
                snippets=snippets,
            ),
            schema=ANSWER_SCHEMA,
        )
        claims = [
            Claim(
                claim_id=item["claim_id"],
                kind=item["kind"],
                statement=item["statement"],
                snippet_ids=list(item.get("snippet_ids", [])),
                supersedes_claim_ids=list(item.get("supersedes_claim_ids", [])),
            )
            for item in raw["claims"]
        ]
        return AnswerPayload(
            answer_markdown=raw["answer_markdown"],
            claims=claims,
            open_questions=list(raw.get("open_questions", [])),
            needs_more_evidence=bool(raw.get("needs_more_evidence", False)),
        )

    def _generate_audit(
        self,
        *,
        question: str,
        prior_turn_ledger: str,
        rendered_answer: str,
        answer: AnswerPayload,
        verifier,
        snippets: list[Snippet],
    ) -> AuditReport:
        raw = self.client.create_structured_output(
            model=self.audit_model,
            instructions=AUDIT_INSTRUCTIONS,
            user_content=build_audit_prompt(
                question=question,
                prior_turn_ledger=prior_turn_ledger,
                rendered_answer=rendered_answer,
                answer=answer,
                verifier=verifier,
                snippets=snippets,
            ),
            schema=AUDIT_SCHEMA,
        )
        findings = [
            AuditFinding(
                severity=item["severity"],
                title=item["title"],
                detail=item["detail"],
                claim_ids=list(item.get("claim_ids", [])),
                snippet_ids=list(item.get("snippet_ids", [])),
            )
            for item in raw["findings"]
        ]
        return AuditReport(
            verdict=raw["verdict"],
            summary=raw["summary"],
            findings=findings,
            missing_checks=list(raw.get("missing_checks", [])),
        )

    def _preferred_paths(self, session: InvestigationSession, question: str) -> list[str]:
        preferred: list[str] = []
        if session.repo_ref.subpath:
            preferred.append(session.repo_ref.subpath)

        if session.turns and re.search(
            r"\b(this|that|it|they|earlier|previous|third|second|first)\b", question.lower()
        ):
            last_turn = session.turns[-1]
            preferred.extend({snippet.path for snippet in last_turn.snippets[:4]})

        for turn in session.turns[-3:]:
            if turn.question.lower() in question.lower():
                preferred.extend({snippet.path for snippet in turn.snippets[:3]})

        deduped: list[str] = []
        seen = set()
        for path in preferred:
            if path not in seen:
                deduped.append(path)
                seen.add(path)
        return deduped[:8]


def render_answer(markdown: str, snippets: list[Snippet]) -> str:
    mapping = {snippet.snippet_id: snippet.label() for snippet in snippets}

    def replace(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split(",")]
        labels = [mapping.get(part, f"{part}?") for part in parts]
        return "[" + "; ".join(labels) + "]"

    return re.sub(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", replace, markdown)


def format_turn(turn: TurnRecord) -> str:
    lines = [
        f"Turn {turn.turn_number}",
        "",
        turn.rendered_answer.strip(),
        "",
        f"Verification: {turn.verifier.verdict}",
    ]
    for issue in turn.verifier.issues:
        lines.append(f"- {issue.severity.upper()}: {issue.message}")

    lines.extend(
        [
            "",
            f"Independent audit: {turn.audit.verdict}",
            turn.audit.summary.strip(),
        ]
    )
    for finding in turn.audit.findings:
        lines.append(f"- {finding.severity.upper()}: {finding.title} - {finding.detail}")

    if turn.answer.open_questions:
        lines.extend(["", "Open questions:"])
        for item in turn.answer.open_questions:
            lines.append(f"- {item}")

    return "\n".join(lines).strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
