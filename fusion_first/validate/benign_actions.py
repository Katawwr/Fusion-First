"""Actions the user asked for: how often does the runtime guard block them?

InjecAgent's attacker cases with roles swapped (the user asks for the action in the attacker's words),
plus its user cases, each through the guard in its strictest posture. Cases whose attacker tools
appeared in the development samples are `dev`; the rest are `heldout`. A call's arguments are only
values the request gives, so a block comes from the rules, not invented payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fusion_first.guardrail.guard import Guardrail, _tool_words
from fusion_first.guardrail.policy import GuardConfig
from fusion_first.validate.experiments import SPENT, _load, build_items

_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_SEND_WORDS = {"send", "email", "forward", "share", "post", "upload"}
# Values a request spells out: quoted strings, then ids / amounts (any token with a digit).
_QUOTED = re.compile(r"'([^']{1,80})'|\"([^\"]{1,80})\"")
_ID = re.compile(r"(?<![\w@.])[A-Za-z_\-]*\d[\w\-]*")


@dataclass(frozen=True)
class BenignCase:
    case_id: str
    kind: str  # dh | ds (a swapped attacker case) | user (one of InjecAgent's user cases)
    request: str
    tools: tuple[str, ...]

    def calls(self) -> list[tuple[str, dict]]:
        to = _EMAIL.findall(self.request)
        text = _EMAIL.sub(" ", self.request)
        values = [a or b for a, b in _QUOTED.findall(text)] + _ID.findall(_QUOTED.sub(" ", text))
        out = []
        for t in self.tools:
            args = {"to": to[0]} if to and _SEND_WORDS & set(_tool_words(t)) else {}
            args.update({f"value_{i}": v.strip(" .,") for i, v in enumerate(values) if v.strip(" .,")})
            out.append((t, args))
        return out


def build_cases(rows: list[dict] | None = None) -> list[BenignCase]:
    rows = rows if rows is not None else _load("injecagent")
    attacker: dict[tuple, BenignCase] = {}
    user: dict[str, BenignCase] = {}
    for r in rows:
        tools = tuple(r["attacker_tools"])
        attacker.setdefault(tools, BenignCase("benign:" + "+".join(tools), r["kind"], r["attacker_instruction"], tools))
        user.setdefault(r["user_tool"], BenignCase("user:" + r["user_tool"], "user", r["user_instruction"],
                                                   (r["user_tool"],)))
    return sorted(attacker.values(), key=lambda c: c.case_id) + sorted(user.values(), key=lambda c: c.case_id)


def dev_attacker_tools() -> set[tuple[str, ...]]:
    """Attacker tool sets of every item in the spent development samples."""
    return {tuple(it.oracle["forbidden_tools"]) for spec in SPENT
            for it in build_items("injecagent", spec[1], salt=spec[0], exclude=spec[2] if len(spec) > 2 else None)}


def split_of(case: BenignCase, dev: set[tuple[str, ...]]) -> str:
    return "dev" if case.kind == "user" or case.tools in dev else "heldout"


def evaluate(case: BenignCase, config: GuardConfig | None = None) -> dict:
    """Every call of the case through the guard; the case is wrongly blocked if any call is blocked."""
    guard = Guardrail(config or GuardConfig(require_authorization=True))
    blocked = []
    for tool, args in case.calls():
        out = guard.guard_tool_call(tool, args, user_request=case.request, untrusted_context=True)
        if out.blocked:
            blocked.append({"tool": tool, "rules": sorted({_rule(e.detail) for e in out.events}),
                            "detail": "; ".join(e.detail for e in out.events)})
    return {"case_id": case.case_id, "kind": case.kind, "blocked": bool(blocked), "blocked_calls": blocked}


def _rule(detail: str) -> str:
    if "not covered by the user's request" in detail:
        return "request"
    if "private data" in detail:
        return "private_read"
    return "destination"  # external destination or secret/PII shipping: the pre-existing rules
