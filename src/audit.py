from __future__ import annotations

import re

from models import AnswerPayload, AuditFinding, AuditReport, Snippet, VerifierIssue, VerifierReport

SNIPPET_REF_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")


def verify_answer(answer: AnswerPayload, snippets: list[Snippet]) -> VerifierReport:
    known_ids = {snippet.snippet_id for snippet in snippets}
    cited_ids = sorted(_snippet_ids_from_text(answer.answer_markdown))
    unknown_ids = sorted(snippet_id for snippet_id in cited_ids if snippet_id not in known_ids)
    issues: list[VerifierIssue] = []

    if unknown_ids:
        issues.append(
            VerifierIssue(
                severity="high",
                message=f"Answer referenced unknown snippets: {', '.join(unknown_ids)}",
            )
        )

    uncited_claim_ids: list[str] = []
    for claim in answer.claims:
        missing = [snippet_id for snippet_id in claim.snippet_ids if snippet_id not in known_ids]
        if missing:
            issues.append(
                VerifierIssue(
                    severity="high",
                    message=(
                        f"Claim {claim.claim_id} referenced unknown snippets: {', '.join(missing)}"
                    ),
                    claim_id=claim.claim_id,
                )
            )
        if claim.kind in {"observation", "risk", "recommendation"} and not claim.snippet_ids:
            uncited_claim_ids.append(claim.claim_id)
            issues.append(
                VerifierIssue(
                    severity="medium",
                    message=f"Claim {claim.claim_id} has no supporting snippets.",
                    claim_id=claim.claim_id,
                )
            )

    if not cited_ids:
        issues.append(
            VerifierIssue(severity="medium", message="Answer text did not cite any snippets.")
        )

    verdict = "pass"
    if any(issue.severity == "high" for issue in issues):
        verdict = "fail"
    elif issues:
        verdict = "warn"

    return VerifierReport(
        verdict=verdict,
        issues=issues,
        cited_snippet_ids=cited_ids,
        unknown_snippet_ids=unknown_ids,
        uncited_claim_ids=uncited_claim_ids,
    )


def empty_audit_from_verifier(verifier: VerifierReport) -> AuditReport:
    findings = [
        AuditFinding(
            severity="high" if issue.severity == "high" else "medium",
            title="Programmatic verifier issue",
            detail=issue.message,
            claim_ids=[issue.claim_id] if issue.claim_id else [],
            snippet_ids=[],
        )
        for issue in verifier.issues
    ]
    verdict = "fail" if verifier.verdict == "fail" else "warn"
    summary = (
        "Independent audit skipped because programmatic verification already found blocking issues."
    )
    return AuditReport(verdict=verdict, summary=summary, findings=findings, missing_checks=[])


def _snippet_ids_from_text(text: str) -> set[str]:
    results: set[str] = set()
    for match in SNIPPET_REF_RE.finditer(text):
        for raw in match.group(1).split(","):
            results.add(raw.strip())
    return results
