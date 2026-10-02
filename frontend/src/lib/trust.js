import { ERROR_KINDS, pct } from "./jargon";

export function scoredSentence(trust) {
  if (!trust || !trust.n_planned) return null;
  const { n_scored, n_planned, n_errored, error_kinds = {} } = trust;
  if (!n_errored) return `${n_scored} of ${n_planned} attacks scored`;
  const reasons = Object.entries(error_kinds)
    .map(([k, n]) => `${n} × ${ERROR_KINDS[k] || k}`)
    .join(", ");
  return `${n_scored} of ${n_planned} attacks scored: ${n_errored} unscored (${reasons}); unscored attacks are never counted as safe`;
}

// Plain sentence for the paired change. `point` = baseline rate − hardened rate (positive = fewer
// issues with the fix). Never renders "−-10%": a regression is named as one.
export function deltaSentence(point, quality) {
  const size = pct(Math.abs(point || 0));
  if (!point) return quality ? "Quality unchanged by the fixed prompt" : "No change in attacks that get through";
  if (quality) {
    return point > 0
      ? `${size} fewer answers with a defect using the fixed prompt`
      : `${size} more answers with a defect using the fixed prompt: the fix costs quality`;
  }
  return point > 0
    ? `${size} fewer attacks get through with the fix`
    : `${size} more attacks get through with the fix: a regression`;
}
