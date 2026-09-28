// The report's headline sentence — derived from what was actually measured, never a canned boast.
import { pct } from "./jargon";

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

  let sentence;
  if (worstBaseline === 0) {
    sentence = "No attack got through on the original prompt.";
  } else {
    sentence = `Worst check: ${pct(worstBaseline)} of attacks got through on the original prompt.`;
    if (regressed.length) {
      sentence += ` Warning: the fix made ${regressed.length === 1 ? "one check" : `${regressed.length} checks`} worse.`;
    } else if (proven.length) {
      sentence += ` The fix gave a significant reduction (PROVEN) on ${proven.length} of ${measured.length} check${measured.length === 1 ? "" : "s"}.`;
    } else {
      sentence += " No check reached PROVEN; each badge below gives the reason.";
    }
  }
  if (partial) sentence += " Some checks had too few scored attacks to grade.";
  return {
    kind: regressed.length ? "regression" : proven.length ? "proven" : "measured",
    headline: `${result?.target_name || "Your prompt"}: grade ${grade}`,
    sentence,
  };
}
