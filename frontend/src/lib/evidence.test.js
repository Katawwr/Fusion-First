import { describe, expect, it } from "vitest";
import { significanceByGrader } from "./evidence";

const b = (p, better) => ({ f1: 0.5, mcnemar_p: p, grader_more_accurate: better });

describe("significanceByGrader", () => {
  it("states the direction of a significant difference, per grader", () => {
    const rows = [
      { grader: "Sonnet", baselines: { naive_regex: b(0.2, true) } },
      { grader: "Sonnet", baselines: { naive_regex: b(0.3, true), tuned_heuristic: b(0.4, true) } },
      { grader: "Local", baselines: { naive_regex: b(0.009, false), tuned_heuristic: b(0.5, false) } },
    ];
    const [sonnet, local] = significanceByGrader(rows);
    expect(sonnet).toBe(
      "Sonnet: scores higher than the rule-based checks; no difference is significant yet.",
    );
    expect(local).toBe("Local: significantly less accurate than a rule-based check in 1 of 2 comparisons.");
  });

  it("never claims the grader scores higher when it doesn't", () => {
    const [s] = significanceByGrader([{ grader: "G", baselines: { naive_regex: b(0.4, false) } }]);
    expect(s).toBe("G: no difference from the rule-based checks is significant yet.");
    const [win] = significanceByGrader([{ grader: "G", baselines: { naive_regex: b(0.01, true) } }]);
    expect(win).toBe("G: significantly more accurate than a rule-based check in 1 of 1 comparisons.");
  });
});
