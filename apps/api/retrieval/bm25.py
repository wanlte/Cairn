from __future__ import annotations

import math
import re

import jieba

_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token for token in jieba.lcut(text.lower()) if token and not _PUNCT.fullmatch(token)]


class BM25:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs: dict[int, list[str]] = {}
        self.doc_len: dict[int, int] = {}
        self.avg_len = 0.0
        self.tf: dict[int, dict[str, int]] = {}
        self.df: dict[str, int] = {}

    def fit(self, docs: dict[int, str]) -> None:
        self.docs = {doc_id: tokenize(text) for doc_id, text in docs.items()}
        self.doc_len = {doc_id: len(tokens) for doc_id, tokens in self.docs.items()}
        self.avg_len = (
            sum(self.doc_len.values()) / len(self.doc_len) if self.doc_len else 0.0
        )
        self.tf = {
            doc_id: {token: tokens.count(token) for token in set(tokens)}
            for doc_id, tokens in self.docs.items()
        }
        self.df = {}
        for tokens in self.docs.values():
            for token in set(tokens):
                self.df[token] = self.df.get(token, 0) + 1

    def scores(self, query: str) -> dict[int, float]:
        if not self.docs:
            return {}
        query_tokens = tokenize(query)
        total = len(self.docs)
        result: dict[int, float] = {}
        for doc_id in self.docs:
            score = 0.0
            length_norm = 1 - self.b + self.b * (
                self.doc_len[doc_id] / self.avg_len if self.avg_len else 0
            )
            for token in query_tokens:
                if token not in self.tf[doc_id]:
                    continue
                freq = self.tf[doc_id][token]
                doc_freq = self.df.get(token, 0)
                idf = math.log(1 + (total - doc_freq + 0.5) / (doc_freq + 0.5))
                score += idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * length_norm
                )
            result[doc_id] = score
        return result
