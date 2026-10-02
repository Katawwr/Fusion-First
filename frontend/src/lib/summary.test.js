import { describe, expect, it } from "vitest";
import { guardInSample, summarize } from "./summary";
import fixture from "./guardInSample.fixture.json";

describe("guardInSample", () => {
  // The same cases tests/test_guard_replay.py checks against the Python replay.
  for (const c of fixture.cases) {
    it(`mirrors the Python replay: ${c.name}`, () => {
      expect(guardInSample({ outcomes: c.outcomes, cards: c.cards })).toEqual(c.expected);
    });
  }

  it("claims nothing for a missing result", () => {
    expect(guardInSample(null)).toBeNull();
  });
});

const card = (grade, base, hard, honesty = "PRELIMINARY") => ({
  grade,
  before_after: { baseline_issue_rate: base, hardened_issue_rate: hard, honesty },
});

describe("summarize", () => {
  it("labels canned demo results as an example that did not run your prompt", () => {
    const s = summarize({ execution: "canned", demonstration: true, overall_grade: "F", cards: [card("F", 1, 0)] });
    expect(s.kind).toBe("example");
    expect(s.headline).toBe("Example Report");
    expect(s.sentence).not.toMatch(/moves the needle/);
  });

  it("never grades when nothing could be scored", () => {
    const s = summarize({ execution: "live", overall_grade: "?", cards: [{ grade: "?" }] });
    expect(s.kind).toBe("unmeasured");
    expect(s.sentence).toMatch(/never counted as safe|nothing unscored was counted as safe/);
  });

  it("says plainly when nothing got through", () => {
    const s = summarize({ execution: "live", overall_grade: "A", cards: [card("A", 0, 0)] });
    expect(s.sentence).toMatch(/No attack got through on the prompt as written/);
  });

  it("leads with the measurement; the prompt fix comes second", () => {
    const s = summarize({ execution: "live", overall_grade: "F", cards: [card("F", 0.9, 0.1)] });
    expect(s.sentence).toMatch(/^Worst check: 90% of attacks got through on the prompt as written\. /);
    expect(s.sentence.indexOf("prompt fix")).toBeGreaterThan(s.sentence.indexOf("as written"));
  });

  it("warns when the fix made things worse", () => {
    const s = summarize({ execution: "live", overall_grade: "C", cards: [card("C", 0.2, 0.4)] });
    expect(s.kind).toBe("regression");
    expect(s.sentence).toMatch(/Warning: the prompt fix made one check worse/);
  });

  it("only claims a significant reduction when PROVEN", () => {
    const proven = summarize({ execution: "live", overall_grade: "F", cards: [card("F", 0.9, 0.1, "PROVEN")] });
    expect(proven.sentence).toMatch(/The prompt fix gave a significant reduction \(PROVEN\) on 1 of 1 check\./);
    const prelim = summarize({ execution: "live", overall_grade: "F", cards: [card("F", 0.9, 0.1)] });
    expect(prelim.sentence).not.toMatch(/gave a significant reduction/);
    // PRELIMINARY can still have p < 0.05 (too few pairs), so the sentence never says "not significant".
    expect(prelim.sentence).toMatch(/No check reached PROVEN with the prompt fix; each badge below gives the reason\./);
    expect(prelim.sentence).not.toMatch(/No significant/);
  });

  it("warns about a fix that made things worse even when nothing got through as written", () => {
    const s = summarize({ execution: "live", overall_grade: "A", cards: [card("A", 0, 0.2)] });
    expect(s.kind).toBe("regression");
    expect(s.sentence).toBe("No attack got through on the prompt as written. Warning: the prompt fix made one check worse.");
  });

  it("flags partially graded reports", () => {
    const s = summarize({ execution: "live", overall_grade: "?", cards: [card("D", 0.4, 0.1), { grade: "?" }] });
    expect(s.sentence).toMatch(/too few scored attacks/);
  });
});

import { deltaSentence } from "./trust";

describe("deltaSentence", () => {
  it("never renders a double negative and names regressions", () => {
    expect(deltaSentence(0.5, false)).toBe("50% fewer attacks get through with the fix");
    expect(deltaSentence(-0.1, false)).toMatch(/10% more attacks .* regression/);
    expect(deltaSentence(-0.2, true)).toMatch(/20% more answers with a defect .* costs quality/);
    expect(deltaSentence(0, true)).toBe("Quality unchanged by the fixed prompt");
    expect(deltaSentence(0.25, false)).not.toMatch(/−-|--/);
  });
});
