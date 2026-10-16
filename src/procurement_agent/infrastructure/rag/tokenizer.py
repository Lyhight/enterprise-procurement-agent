from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/Latin policy text without external services."""
    normalized = text.lower()
    terms = re.findall(r"[a-z0-9]+", normalized)
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        terms.append(run)
        terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return terms
