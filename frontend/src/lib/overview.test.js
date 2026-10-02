import { describe, expect, it } from "vitest";
import evidence from "../content/evidence.json";
import { findings, headlineStats, limitations, resultGroups } from "./overview";

describe("resultGroups", () => {
  const groups = resultGroups(evidence);
  const ids = groups.map((g) => g.id);

  it("leads with the guard and ends with the negative results", () => {
    expect(ids[0]).toBe("step3");
    expect(ids).toContain("step2");
    expect(ids).toContain("judge");
    expect(ids.at(-1)).toBe("negative");
  });

  it("takes every estimate from the evidence, with its interval", () => {
    const v3 = evidence.step3_guard.arms.v3;
    const row = groups.find((g) => g.id === "step3").rows[0];
    expect(row.est).toBe(v3.recall);
    expect(row.n).toBe(v3.attacks);
    for (const r of groups.flatMap((g) => g.rows)) {
      expect(r.est).toEqual(expect.objectContaining({ point: expect.any(Number), low: expect.any(Number), high: expect.any(Number) }));
    }
  });

  it("states the prompt fix's measured cost and the rubric's non-result", () => {
    const neg = groups.find((g) => g.id === "negative").rows.map((r) => r.label);
    expect(neg.some((l) => /Rubric grading minus one plain question/.test(l))).toBe(true);
    expect(neg.some((l) => /safe requests refused/.test(l))).toBe(true);
  });

  it("shows the guard's measured cost in a live agent loop, whatever the decision", () => {
    const s4 = evidence.step4_agentdojo;
    const g = groups.find((x) => x.id === "step4");
    expect(g.rows.map((r) => r.est)).toEqual(expect.arrayContaining([s4.utility_benign.none, s4.utility_benign.v3]));
    expect(g.note).toMatch(s4.comparisons.cost_none_vs_v3.non_inferior ? /within the registered margin/ : /over the registered margin/);
    expect(findings(evidence).join(" ")).toMatch(/live agent loop/);
  });

  it("drops a guard block that was not adopted", () => {
    const notAdopted = { ...evidence, step3_guard: { ...evidence.step3_guard, decision: "not adopted" } };
    expect(resultGroups(notAdopted).map((g) => g.id)).not.toContain("step3");
  });

  it("claims nothing without evidence", () => {
    expect(resultGroups({})).toEqual([]);
    expect(findings({})).toEqual([]);
  });

  it("marks a grader below the policy floor", () => {
    const local = groups.find((g) => g.id === "judge").rows.filter((r) => /local/.test(r.label));
    if (evidence.local_grader && !evidence.local_grader.meets_floor) {
      expect(local.length).toBeGreaterThan(0);
      for (const r of local) expect(r.detail).toBe("below the policy floor");
    }
  });
});

describe("findings and limitations", () => {
  it("never claims the rubric is more accurate", () => {
    const text = findings(evidence).join(" ");
    expect(text).not.toMatch(/rubric (judge |grading )?is more accurate/i);
    if (!evidence.rubric_vs_plain.claim_allowed) expect(text).toMatch(/not more accurate than one plain question/);
  });

  it("names the fix as optional", () => {
    expect(findings(evidence).join(" ")).toMatch(/It is optional/);
  });

  it("lists the models the results were measured on", () => {
    const text = limitations(evidence).join(" ");
    for (const m of evidence.step2_guard.models) expect(text).toContain(m);
    expect(text).toMatch(/not a sandbox/);
  });
});

describe("headlineStats", () => {
  it("leads with the guard against Llama Guard 3, every figure from the evidence", () => {
    const stats = headlineStats(evidence);
    const s2 = evidence.step2_guard.systems;
    expect(stats[0].value).toBe(`${Math.round(s2.fusion.recall.point * 100)}%`);
    expect(stats[1].value).toBe(`${Math.round(s2.llama_guard_b.recall.point * 100)}%`);
    expect(stats.map((x) => x.label).join(" ")).toMatch(/Llama Guard 3/);
    for (const x of stats) expect(x.value).toMatch(/^\d+%$/);
  });

  it("claims nothing without adopted evidence", () => {
    expect(headlineStats({})).toEqual([]);
  });
});
