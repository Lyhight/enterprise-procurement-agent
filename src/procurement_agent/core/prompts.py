from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    content: str


def load_prompt(filename: str) -> PromptTemplate:
    text = files("procurement_agent.prompts").joinpath(filename).read_text(encoding="utf-8")
    metadata, content = _split_frontmatter(text)
    return PromptTemplate(
        name=metadata.get("name", filename),
        version=metadata.get("version", "unversioned"),
        content=content.strip(),
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    _, header, body = text.split("---", 2)
    metadata = {}
    for line in header.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, body
