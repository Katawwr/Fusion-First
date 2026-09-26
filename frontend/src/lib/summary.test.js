import { describe, expect, it } from "vitest";
import { summarize } from "./summary";

const card = (grade, base, hard, honesty = "PRELIMINARY") => ({
  grade,
  before_after: { baseline_issue_rate: base, hardened_issue_rate: hard, honesty },
});

describe("summarize", () => {
  it("labels canned demo results as an example that did not run your prompt", () => {
    const s = summarize({ execution: "canned", demonstration: true, overall_grade: "F", cards: [card("F", 1, 0)] });
    expect(s.kind).toBe("example");
    expect(s.headline).toMatch(/your prompt was not run/);
    expect(s.sentence).not.toMatch(/moves the needle/);
  });

  it("never grades when nothing could be scored", () => {
    const s = summarize({ execution: "live", overall_grade: "?", cards: [{ grade: "?" }] });
    expect(s.kind).toBe("unmeasured");
    expect(s.sentence).toMatch(/never counted as safe|nothing unscored was counted as safe/);
  });

  it("says plainly when nothing got through", () => {
    const s = summarize({ execution: "live", overall_grade: "A", cards: [card("A", 0, 0)] });
    expect(s.sentence).toMatch(/None of the attacks got through/);
  });

  it("warns when the fix made things worse", () => {
    const s = summarize({ execution: "live", overall_grade: "C", cards: [card("C", 0.2, 0.4)] });
    expect(s.kind).toBe("regression");
    expect(s.sentence).toMatch(/made one test worse/);
  });

  it("only claims a measured reduction when PROVEN", () => {
    const proven = summarize({ execution: "live", overall_grade: "F", cards: [card("F", 0.9, 0.1, "PROVEN")] });
    expect(proven.sentence).toMatch(/measurably reduced/);
    const prelim = summarize({ execution: "live", overall_grade: "F", cards: [card("F", 0.9, 0.1)] });
    expect(prelim.sentence).not.toMatch(/measurably reduced/);
    expect(prelim.sentence).toMatch(/how sure we can be/);
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
