// The report's headline sentence, derived from what was actually measured.
import { pct } from "./jargon";

const REPLAY_SETUP =
  "Guard set up as the snippet: your system prompt, the code-shaped values it marks secret (like OVR-4471), no domain allowlist; secrets you would list yourself are not included.";

const plural = (n, word, many = `${word}s`) => (n === 1 ? word : many);

function countReplay(outcomes) {
  const through = outcomes.filter((o) => o.baseline_issue === true);
  const clean = outcomes.filter((o) => o.baseline_issue === false);
  const replayable = through.filter((o) => o.guard_replay !== "no_tool_call");
  return {
    stopped: replayable.filter((o) => o.guard_replay === "stopped").length,
    got_through: replayable.length,
    in_prose: through.length - replayable.length,
    acted_on_clean: clean.filter((o) => o.guard_replay === "stopped").length,
    clean_leaks: clean.filter((o) => o.guard_replay === "stopped" && o.guard_leak).length,
    clean: clean.length,
  };
}

function replaySentence(s) {
  const clauses = [];
  if (s.got_through) clauses.push(`${s.stopped} of ${s.got_through} ${plural(s.got_through, "attack")} that got through`);
  if (s.clean) {
    const leaks = s.clean_leaks ? ` (${s.clean_leaks} carried a secret or your system prompt)` : "";
    clauses.push(`${s.acted_on_clean} of ${s.clean} ${plural(s.clean, "reply", "replies")} graded clean${leaks}`);
  }
  const parts = [];
  if (!s.got_through && !s.in_prose) parts.push("none got through");
  if (clauses.length) parts.push(`the guard blocked or redacted ${clauses.join(" and ")}`);
  if (s.in_prose) {
    parts.push(`${s.in_prose} ${plural(s.in_prose, "attack")} got through in prose, with no tool call for the guard to check`);
  }
  let line = `In-sample, this scan's own attacks: ${parts.join("; ")}.`;
  if (s.withheld_checks.length) {
    line += ` Not counted (grade withheld): ${s.withheld_checks.map((c) => c.replace(/_/g, " ")).join(", ")}.`;
  }
  return line;
}

// The scan's in-sample guard replay: mirrors fusion_first/engine/guard_replay.py (in_sample_payload), kept
// in step by the shared guardInSample.fixture.json. Null when nothing was replayed (demo scans, results
// from before the replay existed, only withheld grades).
export function guardInSample(result) {
  const withheld = [...new Set((result?.cards || []).filter((c) => c.grade === "?").map((c) => c.check))].sort();
  const judged = (result?.outcomes || []).filter(
    (o) => o.guard_replay != null && o.baseline_issue != null && !withheld.includes(o.check),
  );
  if (!judged.length) return null;
  const by_check = {};
  for (const check of [...new Set(judged.map((o) => o.check))]) {
    by_check[check] = countReplay(judged.filter((o) => o.check === check));
  }
  const s = { ...countReplay(judged), by_check, withheld_checks: withheld };
  return { ...s, sentence: replaySentence(s), setup: REPLAY_SETUP };
}

const isCanned = (result) =>
  result?.execution === "canned" || (result?.execution == null && result?.demonstration);

export function summarize(result) {
  const cards = result?.cards || [];
  const grade = result?.overall_grade || "?";

  if (isCanned(result)) {
    return {
      kind: "example",
      headline: "Example Report",
      sentence: "",
    };
  }

  const measured = cards.filter((c) => c.grade && c.grade !== "?");
  if (!measured.length) {
    return {
      kind: "unmeasured",
      headline: `${result?.target_name || "Your prompt"}: not enough evidence to grade`,
      sentence: "Each check below gives the reason. Unscored attacks are never counted as safe.",
    };
  }

  const worstBaseline = Math.max(0, ...measured.map((c) => c.before_after?.baseline_issue_rate || 0));
  const regressed = measured.filter(
    (c) => (c.before_after?.hardened_issue_rate || 0) > (c.before_after?.baseline_issue_rate || 0),
  );
  const proven = measured.filter((c) => c.before_after?.honesty === "PROVEN");
  const partial = measured.length < cards.length;

  const worse = ` Warning: the prompt fix made ${regressed.length === 1 ? "one check" : `${regressed.length} checks`} worse.`;
  let sentence;
  if (worstBaseline === 0) {
    sentence = "No attack got through on the prompt as written.";
    if (regressed.length) sentence += worse;
  } else {
    sentence = `Worst check: ${pct(worstBaseline)} of attacks got through on the prompt as written.`;
    if (regressed.length) {
      sentence += worse;
    } else if (proven.length) {
      sentence += ` The prompt fix gave a significant reduction (PROVEN) on ${proven.length} of ${measured.length} check${measured.length === 1 ? "" : "s"}.`;
    } else {
      // Not "not significant": PRELIMINARY can still have p < 0.05 with too few pairs.
      sentence += " No check reached PROVEN with the prompt fix; each badge below gives the reason.";
    }
  }
  if (partial) sentence += " Some checks had too few scored attacks to grade.";
  return {
    kind: regressed.length ? "regression" : proven.length ? "proven" : "measured",
    headline: `${result?.target_name || "Your prompt"}: grade ${grade}`,
    sentence,
  };
}
