from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import log

from .embeddings import LocalHashEmbedding
from .tokenizer import tokenize


@dataclass(frozen=True)
class RetrievalDocument:
    source: str
    section: str
    content: str


@dataclass(frozen=True)
class RankedDocument:
    document: RetrievalDocument
    score: float
    lexical_score: float
    vector_score: float


class HybridPolicyRetriever:
    """BM25 + dense-vector retrieval with deterministic reciprocal scoring."""

    def __init__(
        self,
        documents: list[RetrievalDocument],
        embedding: LocalHashEmbedding | None = None,
        lexical_weight: float = 0.65,
    ) -> None:
        self.documents = documents
        self.embedding = embedding or LocalHashEmbedding()
        self.lexical_weight = lexical_weight
        self._tokens = [tokenize(item.content + " " + item.section) for item in documents]
        self._counts = [Counter(tokens) for tokens in self._tokens]
        self._average_length = (
            sum(len(tokens) for tokens in self._tokens) / len(self._tokens)
            if self._tokens
            else 0.0
        )
        self._vectors = [
            self.embedding.embed(item.section + " " + item.content)
            for item in documents
        ]

    def search(self, query: str, limit: int = 3) -> list[RankedDocument]:
        if not query.strip() or limit < 1 or not self.documents:
            return []
        query_tokens = tokenize(query)
        query_vector = self.embedding.embed(query)
        rows: list[RankedDocument] = []
        for index, document in enumerate(self.documents):
            lexical = self._bm25(query_tokens, index)
            vector = max(self.embedding.similarity(query_vector, self._vectors[index]), 0.0)
            phrase_bonus = 0.15 if query.lower() in document.content.lower() else 0.0
            score = self.lexical_weight * lexical + (1 - self.lexical_weight) * vector + phrase_bonus
            if score > 0:
                rows.append(RankedDocument(document, score, lexical, vector))
        rows.sort(key=lambda row: row.score, reverse=True)
        return rows[:limit]

    def _bm25(self, query_tokens: list[str], document_index: int) -> float:
        if not query_tokens or not self._average_length:
            return 0.0
        counts = self._counts[document_index]
        length = len(self._tokens[document_index])
        score = 0.0
        for term in set(query_tokens):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            document_frequency = sum(1 for row in self._counts if term in row)
            inverse_frequency = log(
                1 + (len(self.documents) - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * length / self._average_length)
            score += inverse_frequency * frequency * 2.5 / denominator
        return score
