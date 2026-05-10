from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from models import Snippet

STOPWORDS = {
    "a",
    "about",
    "actually",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "better",
    "by",
    "can",
    "code",
    "dead",
    "delete",
    "do",
    "does",
    "feel",
    "flag",
    "for",
    "from",
    "function",
    "handle",
    "here",
    "how",
    "i",
    "in",
    "is",
    "it",
    "layer",
    "me",
    "need",
    "off",
    "of",
    "on",
    "or",
    "risk",
    "risky",
    "safe",
    "service",
    "should",
    "signup",
    "skip",
    "suggest",
    "that",
    "the",
    "this",
    "through",
    "to",
    "walk",
    "what",
    "why",
    "work",
    "works",
    "would",
    "x",
    "y",
    "z",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "vendor",
    "tmp",
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp3",
    ".mp4",
    ".webm",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".lock",
}

SYMBOL_PATTERNS = [
    re.compile(r"^\s*async\s+def\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*def\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*async\s+function\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*function\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*="),
    re.compile(r"^\s*func\s+([A-Za-z_]\w*)"),
]


@dataclass
class SymbolLocation:
    name: str
    path: str
    line_number: int


@dataclass
class FileDocument:
    path: str
    lines: list[str]
    token_counts: Counter[str]
    path_tokens: set[str]
    size_bytes: int

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def line(self, line_number: int) -> str:
        return self.lines[line_number - 1]


class RepositorySnapshot:
    def __init__(self, root: Path, max_file_bytes: int = 250_000, max_files: int = 1_500) -> None:
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self.documents: list[FileDocument] = []
        self.path_map: dict[str, FileDocument] = {}
        self.document_frequency: Counter[str] = Counter()
        self.symbols: dict[str, list[SymbolLocation]] = defaultdict(list)
        self.language_counts: Counter[str] = Counter()
        self.readme_path: str | None = None
        self.readme_excerpt: str = ""
        self._load()

    def overview(self) -> str:
        top_level = sorted({path.split("/", 1)[0] for path in self.path_map})
        files = ", ".join(top_level[:12])
        languages = ", ".join(
            f"{name}:{count}" for name, count in self.language_counts.most_common(8)
        )
        parts = [
            f"Repository root: {self.root.name}",
            f"Indexed text files: {len(self.documents)}",
            f"Top-level entries: {files or '(none)'}",
            f"Detected languages: {languages or '(unknown)'}",
        ]
        if self.readme_path and self.readme_excerpt:
            parts.append(f"README excerpt from {self.readme_path}:\n{self.readme_excerpt}")
        return "\n\n".join(parts)

    def search(
        self,
        question: str,
        preferred_paths: list[str] | None = None,
        max_snippets: int = 12,
    ) -> list[Snippet]:
        preferred_paths = preferred_paths or []
        query_tokens = _query_tokens(question)
        symbol_hints = _symbol_hints(question)

        ranked_docs = self._rank_documents(query_tokens, preferred_paths, symbol_hints)
        snippets: list[Snippet] = []
        snippet_index = 1

        for doc, _doc_score in ranked_docs[:10]:
            windows = self._interesting_windows(doc, query_tokens, symbol_hints)
            for start, end, reason, score in windows[:2]:
                snippet = Snippet(
                    snippet_id=f"S{snippet_index}",
                    path=doc.path,
                    start_line=start,
                    end_line=end,
                    text="\n".join(doc.lines[start - 1 : end]),
                    reason=reason,
                    score=score,
                )
                snippets.append(snippet)
                snippet_index += 1
                if len(snippets) >= max_snippets:
                    return snippets

        if not snippets:
            fallback = self._fallback_snippets(max_snippets=max_snippets)
            for snippet in fallback:
                snippet.snippet_id = f"S{snippet_index}"
                snippets.append(snippet)
                snippet_index += 1
                if len(snippets) >= max_snippets:
                    break

        return snippets

    def _load(self) -> None:
        indexed = 0
        for path in sorted(self.root.rglob("*")):
            if indexed >= self.max_files:
                break
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            if path.stat().st_size > self.max_file_bytes:
                continue

            relative = path.relative_to(self.root).as_posix()
            content = _read_text_file(path)
            if content is None:
                continue

            lines = content.splitlines() or [""]
            tokens = Counter(_tokenize(content))
            path_tokens = set(_tokenize(relative.replace("/", " ")))
            doc = FileDocument(
                path=relative,
                lines=lines,
                token_counts=tokens,
                path_tokens=path_tokens,
                size_bytes=path.stat().st_size,
            )

            self.documents.append(doc)
            self.path_map[relative] = doc
            indexed += 1

            if relative.lower().startswith("readme") and not self.readme_path:
                self.readme_path = relative
                self.readme_excerpt = "\n".join(lines[:40]).strip()

            for token in set(tokens):
                self.document_frequency[token] += 1

            for symbol in self._extract_symbols(doc):
                self.symbols[symbol.name].append(symbol)

            self.language_counts[_language_label(relative)] += 1

    def _extract_symbols(self, doc: FileDocument) -> list[SymbolLocation]:
        results: list[SymbolLocation] = []
        for idx, line in enumerate(doc.lines, start=1):
            for pattern in SYMBOL_PATTERNS:
                match = pattern.search(line)
                if match:
                    results.append(
                        SymbolLocation(name=match.group(1), path=doc.path, line_number=idx)
                    )
                    break
        return results

    def _rank_documents(
        self,
        query_tokens: list[str],
        preferred_paths: list[str],
        symbol_hints: list[str],
    ) -> list[tuple[FileDocument, float]]:
        total_docs = max(len(self.documents), 1)
        ranked: list[tuple[FileDocument, float]] = []

        for doc in self.documents:
            score = 0.0
            for token in query_tokens:
                term_frequency = doc.token_counts.get(token, 0)
                if term_frequency:
                    inverse_df = 1.0 + math.log(
                        (1 + total_docs) / (1 + self.document_frequency.get(token, 0))
                    )
                    score += term_frequency * inverse_df
                elif token in doc.path_tokens:
                    score += 2.0

            for preferred in preferred_paths:
                if preferred and preferred in doc.path:
                    score += 5.0

            for symbol in symbol_hints:
                if symbol in self.symbols:
                    for location in self.symbols[symbol]:
                        if location.path == doc.path:
                            score += 8.0

            if score > 0:
                ranked.append((doc, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def _interesting_windows(
        self,
        doc: FileDocument,
        query_tokens: list[str],
        symbol_hints: list[str],
    ) -> list[tuple[int, int, str, float]]:
        hit_lines: list[tuple[int, float, str]] = []
        lowered_lines = [line.lower() for line in doc.lines]

        for idx, line in enumerate(lowered_lines, start=1):
            line_score = 0.0
            matched_terms: list[str] = []
            for token in query_tokens:
                if token in line:
                    line_score += 1.0
                    matched_terms.append(token)
            if line_score:
                reason = f"matched terms: {', '.join(sorted(set(matched_terms))[:5])}"
                hit_lines.append((idx, line_score, reason))

        for symbol in symbol_hints:
            for location in self.symbols.get(symbol, []):
                if location.path == doc.path:
                    hit_lines.append((location.line_number, 4.0, f"symbol definition for {symbol}"))

        if not hit_lines and doc.path.lower().startswith("readme"):
            return [(1, min(60, doc.line_count), "fallback repository overview", 0.5)]

        merged: list[tuple[int, int, str, float]] = []
        for line_number, score, reason in sorted(hit_lines, key=lambda item: (item[0], -item[1])):
            start = max(1, line_number - 4)
            end = min(doc.line_count, line_number + 4)
            if merged and start <= merged[-1][1] + 1:
                prev_start, prev_end, prev_reason, prev_score = merged[-1]
                merged[-1] = (
                    prev_start,
                    max(prev_end, end),
                    prev_reason if prev_score >= score else reason,
                    max(prev_score, score),
                )
            else:
                merged.append((start, end, reason, score))

        merged.sort(key=lambda item: item[3], reverse=True)
        return merged

    def _fallback_snippets(self, max_snippets: int) -> list[Snippet]:
        snippets: list[Snippet] = []
        candidates = []
        if self.readme_path and self.readme_path in self.path_map:
            candidates.append(self.path_map[self.readme_path])
        candidates.extend(doc for doc in self.documents if doc.path not in {self.readme_path})
        for doc in candidates[:max_snippets]:
            end = min(25, doc.line_count)
            snippets.append(
                Snippet(
                    snippet_id="",
                    path=doc.path,
                    start_line=1,
                    end_line=end,
                    text="\n".join(doc.lines[:end]),
                    reason="fallback repository context",
                    score=0.1,
                )
            )
        return snippets


def _read_text_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", text)]


def _query_tokens(question: str) -> list[str]:
    tokens = [token for token in _tokenize(question) if token not in STOPWORDS and len(token) >= 3]
    if tokens:
        return tokens[:16]
    return _tokenize(question)[:8]


def _symbol_hints(question: str) -> list[str]:
    hints: list[str] = []
    for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question):
        if (
            "_" in raw
            or any(ch.isupper() for ch in raw[1:])
            or raw.endswith("Service")
            or raw.endswith("Controller")
        ):
            hints.append(raw)
    return hints[:8]


def _language_label(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".md": "markdown",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
    }.get(suffix, suffix.lstrip(".") or "plain")
