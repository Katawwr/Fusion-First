// Plain-language coverage line for a card's trust block (shared by the UI and its tests).
import { ERROR_KINDS } from "./jargon";

export function scoredSentence(trust) {
  if (!trust || !trust.n_planned) return null;
  const { n_scored, n_planned, n_errored, error_kinds = {} } = trust;
  if (!n_errored) return `${n_scored} of ${n_planned} attacks scored`;
  const reasons = Object.entries(error_kinds)
    .map(([k, n]) => `${n} × ${ERROR_KINDS[k] || k}`)
    .join(", ");
  return `${n_scored} of ${n_planned} attacks scored — ${n_errored} unscored (${reasons}); unscored attacks are never counted as safe`;
}
