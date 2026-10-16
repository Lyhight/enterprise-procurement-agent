from __future__ import annotations

import re
from pathlib import Path

from ..domain.models import PolicyEvidence
from .rag import HybridPolicyRetriever, RetrievalDocument


class KnowledgeBase:
    """Small, auditable local retriever for enterprise Markdown policies."""

    def __init__(self, documents_dir: Path) -> None:
        self.documents_dir = documents_dir
        self._chunks = self._load_chunks()
        self._retriever = HybridPolicyRetriever(self._chunks)

    @property
    def document_count(self) -> int:
        return len({chunk.source for chunk in self._chunks})

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def search(self, query: str, limit: int = 3) -> list[PolicyEvidence]:
        if not query.strip() or limit < 1:
            return []
        ranked = self._retriever.search(query, limit)
        return [
            PolicyEvidence(
                source=row.document.source,
                section=row.document.section,
                content=row.document.content,
                score=round(row.score, 4),
            )
            for row in ranked
        ]

    @property
    def retrieval_mode(self) -> str:
        return "hybrid_bm25_vector"

    def _load_chunks(self) -> list[RetrievalDocument]:
        chunks: list[RetrievalDocument] = []
        if not self.documents_dir.exists():
            return chunks
        for path in sorted(self.documents_dir.glob("*.md")):
            chunks.extend(_split_markdown(path))
        return chunks


def _split_markdown(path: Path) -> list[RetrievalDocument]:
    text = path.read_text(encoding="utf-8-sig")
    section = path.stem
    buffer: list[str] = []
    chunks: list[RetrievalDocument] = []

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if content:
            chunks.append(
                RetrievalDocument(
                    source=path.name,
                    section=section,
                    content=content,
                )
            )
        buffer.clear()

    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+)$", line.strip())
        if heading:
            flush()
            section = heading.group(1).strip()
        else:
            buffer.append(line)
    flush()
    return chunks
