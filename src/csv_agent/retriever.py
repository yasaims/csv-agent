import re
import unicodedata

from rank_bm25 import BM25Okapi

# ASCII alphanumeric runs become words; other word-character runs (e.g. Japanese) become bigrams.
_TOKEN_PATTERN = re.compile(r"[0-9a-z]+|[^\W0-9a-z_]+")


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    for run in _TOKEN_PATTERN.findall(normalized):
        if run.isascii() or len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


class Retriever:
    def __init__(self, documents: list[str]) -> None:
        self._bm25 = BM25Okapi([tokenize(doc) for doc in documents])

    def search(self, query: str, k: int) -> list[int]:
        """Return indices of the top-k documents sharing at least one term with the query."""
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [i for i in ranked if scores[i] > 0][:k]
