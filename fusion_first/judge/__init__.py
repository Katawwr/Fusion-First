"""The calibrated judge.

Design goals:
- rubric decomposed into binary, evidence-bearing criteria (not one holistic 1-10 score);
- structured JSON output, reason-before-verdict;
- untrusted/injected content is delimited so the judge does not follow it;
- the final verdict is a deterministic function of the binary sub-judgments (auditable);
- NO "assume the response is guilty" framing — neutral, evidence-based;
- self-family guard applied at judge selection (see model.registry).
"""

from fusion_first.judge.judge import Judge, JudgeParseError
from fusion_first.judge.rubric import Criterion, Rubric

__all__ = ["Judge", "JudgeParseError", "Criterion", "Rubric"]
