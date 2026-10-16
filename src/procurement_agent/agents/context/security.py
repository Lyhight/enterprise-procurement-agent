from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextSecurityFinding:
    path: str
    indicator: str


@dataclass(frozen=True)
class ContextSecurityReport:
    safe: bool
    findings: tuple[ContextSecurityFinding, ...] = ()


class ContextSecurityScanner:
    """Detect instruction-like payloads inside untrusted business context."""

    _patterns = (
        (
            "instruction_override",
            re.compile(
                r"\b(?:ignore|disregard|override)\b.{0,60}"
                r"\b(?:instruction|prompt|rule|system|developer)\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "privileged_role_spoofing",
            re.compile(
                r"(?:\b(?:system|developer)\s+(?:message|prompt)\b|"
                r"<\|\s*(?:system|developer)\s*\|>|"
                r"\[\s*(?:system|developer)\s*\])",
                re.IGNORECASE,
            ),
        ),
        (
            "secret_exfiltration",
            re.compile(
                r"\b(?:reveal|print|show|exfiltrate)\b.{0,60}"
                r"\b(?:prompt|secret|token|api[ _-]?key)\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "chinese_instruction_override",
            re.compile(
                r"(?:忽略|无视|覆盖).{0,30}(?:之前|以上|原有|系统)"
                r".{0,30}(?:指令|提示词|规则)",
                re.DOTALL,
            ),
        ),
        (
            "chinese_privileged_instruction",
            re.compile(
                r"(?:你现在是|执行以下指令|泄露.{0,10}提示词|"
                r"伪造.{0,10}(?:工具|审批|系统).{0,10}(?:结果|记录))",
                re.DOTALL,
            ),
        ),
    )

    def __init__(self, max_findings: int = 10) -> None:
        self.max_findings = max_findings

    def scan(self, value: Any) -> ContextSecurityReport:
        findings: list[ContextSecurityFinding] = []
        self._scan_value(value, "$", findings)
        return ContextSecurityReport(safe=not findings, findings=tuple(findings))

    def _scan_value(
        self,
        value: Any,
        path: str,
        findings: list[ContextSecurityFinding],
    ) -> None:
        if len(findings) >= self.max_findings:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                self._scan_value(item, f"{path}.{key}", findings)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._scan_value(item, f"{path}[{index}]", findings)
            return
        if not isinstance(value, str):
            return
        for indicator, pattern in self._patterns:
            if pattern.search(value):
                findings.append(
                    ContextSecurityFinding(path=path, indicator=indicator)
                )
                if len(findings) >= self.max_findings:
                    return
