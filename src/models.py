from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Snippet:
    snippet_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    reason: str
    score: float

    def label(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"

    def to_prompt_block(self) -> str:
        return (
            f"[{self.snippet_id}] {self.label()}\nReason: {self.reason}\n```text\n{self.text}\n```"
        )


@dataclass
class Claim:
    claim_id: str
    kind: str
    statement: str
    snippet_ids: list[str] = field(default_factory=list)
    supersedes_claim_ids: list[str] = field(default_factory=list)


@dataclass
class AnswerPayload:
    answer_markdown: str
    claims: list[Claim]
    open_questions: list[str] = field(default_factory=list)
    needs_more_evidence: bool = False


@dataclass
class VerifierIssue:
    severity: str
    message: str
    claim_id: str | None = None


@dataclass
class VerifierReport:
    verdict: str
    issues: list[VerifierIssue]
    cited_snippet_ids: list[str]
    unknown_snippet_ids: list[str]
    uncited_claim_ids: list[str]


@dataclass
class AuditFinding:
    severity: str
    title: str
    detail: str
    claim_ids: list[str] = field(default_factory=list)
    snippet_ids: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    verdict: str
    summary: str
    findings: list[AuditFinding] = field(default_factory=list)
    missing_checks: list[str] = field(default_factory=list)


@dataclass
class TurnRecord:
    turn_number: int
    timestamp: str
    question: str
    snippets: list[Snippet]
    answer: AnswerPayload
    rendered_answer: str
    verifier: VerifierReport
    audit: AuditReport


def claims_from_dict(items: list[dict[str, Any]]) -> list[Claim]:
    return [
        Claim(
            claim_id=item["claim_id"],
            kind=item["kind"],
            statement=item["statement"],
            snippet_ids=list(item.get("snippet_ids", [])),
            supersedes_claim_ids=list(item.get("supersedes_claim_ids", [])),
        )
        for item in items
    ]


def verifier_issues_from_dict(items: list[dict[str, Any]]) -> list[VerifierIssue]:
    return [
        VerifierIssue(
            severity=item["severity"],
            message=item["message"],
            claim_id=item.get("claim_id"),
        )
        for item in items
    ]


def audit_findings_from_dict(items: list[dict[str, Any]]) -> list[AuditFinding]:
    return [
        AuditFinding(
            severity=item["severity"],
            title=item["title"],
            detail=item["detail"],
            claim_ids=list(item.get("claim_ids", [])),
            snippet_ids=list(item.get("snippet_ids", [])),
        )
        for item in items
    ]


def snippets_from_dict(items: list[dict[str, Any]]) -> list[Snippet]:
    return [Snippet(**item) for item in items]


def turn_from_dict(data: dict[str, Any]) -> TurnRecord:
    return TurnRecord(
        turn_number=data["turn_number"],
        timestamp=data["timestamp"],
        question=data["question"],
        snippets=snippets_from_dict(data["snippets"]),
        answer=AnswerPayload(
            answer_markdown=data["answer"]["answer_markdown"],
            claims=claims_from_dict(data["answer"]["claims"]),
            open_questions=list(data["answer"].get("open_questions", [])),
            needs_more_evidence=bool(data["answer"].get("needs_more_evidence", False)),
        ),
        rendered_answer=data["rendered_answer"],
        verifier=VerifierReport(
            verdict=data["verifier"]["verdict"],
            issues=verifier_issues_from_dict(data["verifier"]["issues"]),
            cited_snippet_ids=list(data["verifier"].get("cited_snippet_ids", [])),
            unknown_snippet_ids=list(data["verifier"].get("unknown_snippet_ids", [])),
            uncited_claim_ids=list(data["verifier"].get("uncited_claim_ids", [])),
        ),
        audit=AuditReport(
            verdict=data["audit"]["verdict"],
            summary=data["audit"]["summary"],
            findings=audit_findings_from_dict(data["audit"].get("findings", [])),
            missing_checks=list(data["audit"].get("missing_checks", [])),
        ),
    )


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
