from __future__ import annotations

import argparse
from pathlib import Path

from engine import CodebaseInvestigator, format_turn
from openai_client import OpenAIClientError, OpenAIResponsesClient
from session import SessionStore
from webapp import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Investigate a GitHub codebase with grounded answers and independent audits."
    )
    parser.add_argument(
        "--session-root",
        default=".investigator/sessions",
        help="Directory where investigation sessions are stored.",
    )
    parser.add_argument("--model", default="gpt-5.5", help="Answering model.")
    parser.add_argument("--audit-model", default="gpt-5.4-mini", help="Independent audit model.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Ask a single question about a repository.")
    ask_parser.add_argument("target", help="GitHub URL or an existing session directory.")
    ask_parser.add_argument("question", nargs="+", help="Question to investigate.")

    chat_parser = subparsers.add_parser("chat", help="Start an interactive investigation session.")
    chat_parser.add_argument("target", help="GitHub URL or an existing session directory.")

    serve_parser = subparsers.add_parser("serve", help="Run the web interface.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        try:
            serve(
                host=args.host,
                port=args.port,
                session_root=Path(args.session_root),
                model=args.model,
                audit_model=args.audit_model,
            )
            return 0
        except (OpenAIClientError, Exception) as exc:
            parser.exit(1, f"error: {exc}\n")

    try:
        client = OpenAIResponsesClient()
        store = SessionStore(Path(args.session_root))
        investigator = CodebaseInvestigator(
            client=client,
            model=args.model,
            audit_model=args.audit_model,
        )
        session = store.load_or_create(args.target)
    except (OpenAIClientError, Exception) as exc:
        parser.exit(1, f"error: {exc}\n")

    if args.command == "ask":
        question = " ".join(args.question).strip()
        turn = investigator.ask(session, question)
        print(format_turn(turn))
        return 0

    print(f"Session: {session.session_dir}")
    print("Enter a question. Press Ctrl-D or type :quit to exit.")
    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            print()
            return 0
        if not question:
            continue
        if question in {":quit", ":exit"}:
            return 0
        turn = investigator.ask(session, question)
        print()
        print(format_turn(turn))
        print()
