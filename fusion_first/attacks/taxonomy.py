"""Resolve and validate OWASP crosswalk codes from the pinned YAML."""

from __future__ import annotations

import hashlib
import pathlib

import yaml

from fusion_first._data import data_root
from fusion_first.schemas import OwaspTag

_CROSSWALK = data_root() / "crosswalk" / "owasp_crosswalk.v2025.yaml"


class Crosswalk:
    def __init__(self, path: pathlib.Path = _CROSSWALK):
        self.path = path
        self._data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.llm: dict[str, str] = self._data["llm_2025"]
        self.asi: dict[str, str] = self._data["asi_2026"]
        self.checks: dict[str, dict] = self._data["checks"]
        self.version: str = self._data.get("version", "unknown")

    def code_version(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()[:12]

    def validate_code(self, tag: OwaspTag) -> None:
        if tag.llm and tag.llm not in self.llm:
            raise ValueError(f"unknown LLM code {tag.llm}")
        if tag.asi and tag.asi not in self.asi:
            raise ValueError(f"unknown ASI code {tag.asi}")

    def tag_for_check(self, check: str) -> OwaspTag:
        if check not in self.checks:
            raise KeyError(f"no crosswalk entry for check '{check}'")
        entry = self.checks[check]
        tag = OwaspTag(llm=entry.get("llm"), asi=entry.get("asi"))
        self.validate_code(tag)
        return tag


def crosswalk_version() -> str:
    return Crosswalk().code_version()
