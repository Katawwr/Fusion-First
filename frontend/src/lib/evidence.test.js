import { describe, expect, it } from "vitest";
import { fixVerdict, graderName, guardResult, significanceByGrader } from "./evidence";

const sys = (stopped, attacks, blocked, clean) => ({
  stopped, attacks, blocked, clean,
  recall: { point: stopped / attacks }, over_block: { point: blocked / clean },
});
const step2 = {
  models: ["qwen2.5:7b", "llama3.1:8b"],
  decision: { new_rules: "adopted" },
  systems: { fusion: sys(132, 148, 2, 252), llama_guard_b: sys(77, 148, 24, 252) },
};

describe("guardResult", () => {
  it("states the adopted rules' result with counts, and Llama Guard on the same attacks", () => {
    expect(guardResult(step2)).toBe(
      "Pre-registered test on fresh attacks against qwen2.5:7b and llama3.1:8b: stopped 89% (132 of 148), " +
        "wrongly blocked 1% of clean transcripts (2 of 252). Llama Guard 3, configured, stopped 52%.",
    );
  });

  it("adds the adopted step 3 result (the snippet passes the tool results)", () => {
    const step3 = { decision: "adopted", arms: { v3: { stopped: 75, attacks: 75 }, v2: { stopped: 67, attacks: 75 } },
                    comparisons: { clean: { v3_only: 0, v2_only: 0 } } };
    expect(guardResult(step2, step3)).toMatch(/ On a second fresh InjecAgent sample, given the tool results: stopped 75 of 75 \(67 without them\), no extra wrong blocks\.$/);
    expect(guardResult(step2, { ...step3, decision: "not adopted" })).toBe(guardResult(step2));
  });

  it("claims nothing for rules that were not adopted or not measured", () => {
    expect(guardResult({ ...step2, decision: { new_rules: "not adopted" } })).toBeNull();
    expect(guardResult(undefined)).toBeNull();
  });
});

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


const cell = (point, p, honesty) => ({ before_after: { absolute_reduction: { point }, mcnemar_p: p, honesty } });

describe("fixVerdict", () => {
  it("reads in plain words, with no internal badge names", () => {
    expect(fixVerdict(cell(0.2, 0.3, "PRELIMINARY")).text).toBe("Better with the fix, preliminary");
    expect(fixVerdict(cell(0.2, 0.03, "PRELIMINARY")).text).toBe("Better with the fix, preliminary");
    expect(fixVerdict(cell(-0.1, 0.4, "INCONCLUSIVE")).text).toBe("Worse with the fix, not significant");
    expect(fixVerdict(cell(0.3, 0.001, "PROVEN")).text).toBe("Significantly better with the fix");
    for (const c of [cell(0.2, 0.3, "PRELIMINARY"), cell(0, 1, "INCONCLUSIVE")]) {
      expect(fixVerdict(c).text).not.toMatch(/PRELIMINARY|INCONCLUSIVE|PROVEN|not proven/);
    }
  });
});

describe("graderName", () => {
  it("shortens the evidence's grader descriptions", () => {
    expect(graderName("Claude Sonnet (Claude Code subagent, host-as-judge, fusion-judge rules)")).toBe("Claude Sonnet");
    expect(graderName("qwen2.5:7b probability judge (local)")).toBe("qwen2.5:7b, local");
    expect(graderName("Some grader")).toBe("Some grader");
  });
});
