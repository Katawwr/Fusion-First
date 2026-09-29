// The report's headline sentence — derived from what was actually measured, never a canned boast.
import { pct } from "./jargon";

// The scan's in-sample guard replay (fusion/engine/guard_replay.py): counts over outcomes carrying a
// verdict, overall and per check, and the same sentence the backend prints. Null when nothing was
// replayed (demo scans: their replies are canned; results from before the replay existed).
function countReplay(outcomes) {
  const through = outcomes.filter((o) => o.baseline_issue === true);
  const clean = outcomes.filter((o) => o.baseline_issue === false);
  return {
    stopped: through.filter((o) => o.guard_stopped).length,
    got_through: through.length,
    acted_on_clean: clean.filter((o) => o.guard_stopped).length,
    clean: clean.length,
  };
}

export function guardInSample(result) {
  const judged = (result?.outcomes || []).filter(
    (o) => o.guard_stopped !== null && o.guard_stopped !== undefined && o.baseline_issue !== null && o.baseline_issue !== undefined,
  );
  if (!judged.length) return null;
  const s = countReplay(judged);
  const by_check = {};
  for (const check of [...new Set(judged.map((o) => o.check))]) {
    by_check[check] = countReplay(judged.filter((o) => o.check === check));
  }
  const lead = "In-sample, this scan's own attacks:";
  const cleanPart = `${s.acted_on_clean} of ${s.clean} replies graded clean`;
  const sentence = s.got_through
    ? `${lead} the guard blocked or redacted ${s.stopped} of ${s.got_through} attacks that got through and ${cleanPart}.`
    : `${lead} none got through; the guard blocked or redacted ${cleanPart}.`;
  return { ...s, by_check, sentence };
}

const isCanned = (result) =>
  result?.execution === "canned" || (result?.execution == null && result?.demonstration);

export function summarize(result) {
  const cards = result?.cards || [];
  const grade = result?.overall_grade || "?";

  if (isCanned(result)) {
    return {
      kind: "example",
      headline: "Example report — your prompt was not run",
      sentence:
        "Responses from a deliberately vulnerable sample agent.",
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

  // The measurement leads; the optional prompt fix's paired result follows it.
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
