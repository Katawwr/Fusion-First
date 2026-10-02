// Labels and one-line definitions for the checks and terms the UI shows.

// The four safety checks.
export const CHECKS = {
  direct_prompt_injection: {
    label: "Prompt injection",
    scenario: "Can injected text override your system prompt?",
    owasp: "LLM01 · ASI01",
  },
  excessive_agency: {
    label: "Excessive agency",
    scenario: "Does the agent send, delete, or pay without an explicit request?",
    owasp: "LLM06 · ASI02",
  },
  data_exfiltration: {
    label: "Data exfiltration",
    scenario: "Can the agent be induced to send private data to an untrusted destination?",
    owasp: "LLM02 · ASI03",
  },
  system_prompt_leakage: {
    label: "System prompt leakage",
    scenario: "Does the agent reveal its system prompt or embedded secrets?",
    owasp: "LLM07 · ASI06",
  },
};

// The quality dimension: normal inputs (not attacks), graded by the same judge.
export const QUALITY_CHECKS = {
  instruction_following: {
    label: "Instruction following",
    scenario: "On normal requests, does the agent follow explicit constraints and finish the task?",
  },
};

// Safety or quality: one lookup anywhere a check id is shown.
export function metaFor(check) {
  if (QUALITY_CHECKS[check]) return { owasp: "Quality", ...QUALITY_CHECKS[check] };
  return checkMeta(check);
}

export const isQualityCheck = (check) => Boolean(QUALITY_CHECKS[check]);

export function qualityMeta(check) {
  return (
    QUALITY_CHECKS[check] || {
      label: check.replace(/_/g, " "),
      scenario: "",
    }
  );
}

// Why an attack couldn't be scored (fusion_first/errors.py ErrorKind).
export const ERROR_KINDS = {
  target_error: "target model error",
  target_timeout: "target model timeout",
  judge_error: "grader error",
  judge_timeout: "grader timeout",
  judge_parse: "unreadable grader output",
  rate_limited: "rate limited",
  quota_exhausted: "subscription usage limit reached",
  prompt_too_long: "prompt too long for this backend",
  internal: "internal error",
  unknown: "unknown error",
};

// How independent the grader is from the model it grades.
export const INDEPENDENCE = {
  cross_family: "different model family from the target (strongest)",
  same_family_cross_tier: "same model family, stronger tier",
  same_model: "same model as the target (weakest)",
};

export function checkMeta(check) {
  return (
    CHECKS[check] || {
      label: check.replace(/_/g, " "),
      scenario: "",
      owasp: "",
    }
  );
}

export function pct(x) {
  return `${Math.round((x || 0) * 100)}%`;
}

const RANK = { A: 0, B: 1, C: 2, D: 3, F: 4, "?": 5 };
export function worstGrade(grades) {
  return grades.length
    ? grades.reduce((a, b) => (RANK[b] > RANK[a] ? b : a))
    : "?";
}
