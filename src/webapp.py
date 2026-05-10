from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from engine import CodebaseInvestigator
from openai_client import OpenAIResponsesClient
from session import InvestigationSession, SessionStore


class InvestigatorWebApp:
    def __init__(self, store: SessionStore, investigator: CodebaseInvestigator) -> None:
        self.store = store
        self.investigator = investigator

    def create_session(self, target: str) -> dict[str, object]:
        if not target.strip():
            raise ValueError("A public GitHub URL is required.")
        session = self.store.load_or_create(target.strip())
        return serialize_session(session, include_turns=True)

    def get_session(self, session_id: str) -> dict[str, object]:
        session = self.store.load_by_id(session_id)
        return serialize_session(session, include_turns=True)

    def ask(self, session_id: str, question: str) -> dict[str, object]:
        if not question.strip():
            raise ValueError("A question is required.")

        session = self.store.load_by_id(session_id)
        turn = self.investigator.ask(session, question.strip())
        return {
            "session": serialize_session(session, include_turns=False),
            "turn": serialize_turn(turn),
        }


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def serve(
    *,
    host: str,
    port: int,
    session_root: Path,
    model: str,
    audit_model: str,
) -> None:
    client = OpenAIResponsesClient()
    store = SessionStore(session_root)
    investigator = CodebaseInvestigator(client=client, model=model, audit_model=audit_model)
    app = InvestigatorWebApp(store=store, investigator=investigator)
    static_dir = Path(__file__).resolve().parent / "static"

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle_get_or_head(head_only=False)

        def do_HEAD(self) -> None:
            self._handle_get_or_head(head_only=True)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/session":
                self._handle_create_session()
                return
            if parsed.path == "/api/ask":
                self._handle_ask()
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_get_or_head(self, *, head_only: bool) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._serve_static("index.html", head_only=head_only)
                return
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"}, head_only=head_only)
                return
            if parsed.path.startswith("/api/session/"):
                session_id = unquote(parsed.path[len("/api/session/") :])
                self._handle_get_session(session_id, head_only=head_only)
                return
            self._serve_static(parsed.path.lstrip("/"), head_only=head_only)

        def _handle_create_session(self) -> None:
            try:
                payload = self._read_json_body()
                response = app.create_session(str(payload.get("target", "")))
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, response)

        def _handle_get_session(self, session_id: str, *, head_only: bool = False) -> None:
            try:
                response = app.get_session(session_id)
            except FileNotFoundError:
                self._send_json(
                    HTTPStatus.NOT_FOUND, {"error": "Session not found."}, head_only=head_only
                )
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)}, head_only=head_only)
            except Exception as exc:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)}, head_only=head_only
                )
            else:
                self._send_json(HTTPStatus.OK, response, head_only=head_only)

        def _handle_ask(self) -> None:
            try:
                payload = self._read_json_body()
                response = app.ask(
                    session_id=str(payload.get("session_id", "")),
                    question=str(payload.get("question", "")),
                )
            except FileNotFoundError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Session not found."})
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, response)

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            return payload

        def _serve_static(self, relative_path: str, *, head_only: bool = False) -> None:
            clean_path = relative_path or "index.html"
            requested = (static_dir / clean_path).resolve()
            if static_dir not in requested.parents and requested != static_dir:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, head_only=head_only)
                return
            if not requested.exists() or not requested.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, head_only=head_only)
                return

            content = requested.read_bytes()
            content_type, _ = mimetypes.guess_type(str(requested))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if not head_only:
                self.wfile.write(content)

        def _send_json(
            self, status: HTTPStatus, payload: dict[str, object], *, head_only: bool = False
        ) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

    with ReusableThreadingHTTPServer((host, port), RequestHandler) as httpd:
        print(f"Serving Codebase Investigator at http://{host}:{port}")
        httpd.serve_forever()


def serialize_session(session: InvestigationSession, *, include_turns: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": session.session_dir.name,
        "created_at": session.created_at,
        "turn_count": len(session.turns),
        "repo": {
            "owner": session.repo_ref.owner,
            "repo": session.repo_ref.repo,
            "url": session.repo_ref.original_url,
            "ref": session.repo_ref.ref,
            "subpath": session.repo_ref.subpath,
        },
    }
    if include_turns:
        payload["turns"] = [serialize_turn(turn) for turn in session.turns]
    return payload


def serialize_turn(turn) -> dict[str, object]:
    return {
        "turn_number": turn.turn_number,
        "timestamp": turn.timestamp,
        "question": turn.question,
        "rendered_answer": turn.rendered_answer,
        "answer": {
            "answer_markdown": turn.answer.answer_markdown,
            "claims": [asdict(claim) for claim in turn.answer.claims],
            "open_questions": list(turn.answer.open_questions),
            "needs_more_evidence": turn.answer.needs_more_evidence,
        },
        "snippets": [
            {
                "snippet_id": snippet.snippet_id,
                "label": snippet.label(),
                "path": snippet.path,
                "start_line": snippet.start_line,
                "end_line": snippet.end_line,
                "text": snippet.text,
                "reason": snippet.reason,
                "score": snippet.score,
            }
            for snippet in turn.snippets
        ],
        "verifier": {
            "verdict": turn.verifier.verdict,
            "issues": [asdict(issue) for issue in turn.verifier.issues],
            "cited_snippet_ids": list(turn.verifier.cited_snippet_ids),
            "unknown_snippet_ids": list(turn.verifier.unknown_snippet_ids),
            "uncited_claim_ids": list(turn.verifier.uncited_claim_ids),
        },
        "audit": {
            "verdict": turn.audit.verdict,
            "summary": turn.audit.summary,
            "findings": [asdict(finding) for finding in turn.audit.findings],
            "missing_checks": list(turn.audit.missing_checks),
        },
    }
