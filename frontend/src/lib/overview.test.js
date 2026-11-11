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

describe("the baseline studies", () => {
  const rate = (k, n) => ({ k, n, point: k / n, low: 0, high: 1 });
  const systems = [
    { key: "fusion", label: "Fusion guard" },
    { key: "llama_guard", label: "Llama Guard 3, configured" },
    { key: "prompt_guard_1", label: "Prompt Guard 1" },
    { key: "protectai", label: "ProtectAI deberta-v3 v2" },
  ];
  const each = (f, lg, pg, pa, n) => ({ fusion: rate(f, n), llama_guard: rate(lg, n), prompt_guard_1: rate(pg, n), protectai: rate(pa, n) });
  const study = {
    models: ["qwen2.5:7b", "llama3.1:8b"],
    rules: "5a89479",
    systems,
    baselines: ["llama_guard", "prompt_guard_1", "protectai"],
    sets: {
      plain: { label: "injection as written", attacks: { n: 90, systems: each(88, 50, 40, 55, 90) } },
      enhanced: { label: "with the override prefix", attacks: { n: 100, systems: each(98, 60, 99, 100, 100) } },
    },
    control: { n: 300, systems: each(3, 20, 90, 70, 300) },
    verdicts: {
      plain: { llama_guard: "fusion_better", prompt_guard_1: "fusion_better", protectai: "fusion_better" },
      enhanced: { llama_guard: "fusion_better", prompt_guard_1: "no_significant_difference", protectai: "baseline_better" },
      control: { llama_guard: "fusion_fewer", prompt_guard_1: "fusion_fewer", protectai: "no_significant_difference" },
    },
  };
  const content = {
    verdict: "llama_guard_better",
    systems: [{ key: "llama_guard", label: "Llama Guard 3, off the shelf" }, { key: "fusion", label: "Fusion guard" }],
    unsafe: { n: 300, systems: { llama_guard: rate(250, 300), fusion: rate(0, 300) } },
    safe: { n: 350, systems: { llama_guard: rate(30, 350), fusion: rate(1, 350) } },
  };

  it("lists every system on both attack sets and on the benign runs", () => {
    const [g] = resultGroups({ guard_vs_detectors: study });
    expect(g.id).toBe("detectors");
    expect(g.rows).toHaveLength(12);
    expect(g.rows[0]).toMatchObject({ label: "Fusion guard: attacks stopped, injection as written", n: 90, tone: "good", detail: "88 of 90" });
    expect(g.rows[0].est).toBe(study.sets.plain.attacks.systems.fusion);
    expect(g.rows[7].label).toBe("ProtectAI deberta-v3 v2: attacks stopped, with the override prefix");
    expect(g.rows[8]).toMatchObject({ label: "Fusion guard: benign runs wrongly blocked", tone: "cost", detail: "3 of 300" });
    expect(g.rows.filter((r) => r.tone === "neutral")).toHaveLength(9);
  });

  it("words each verdict as the registered rule gave it, with no numbers", () => {
    expect(findings({ guard_vs_detectors: study })).toEqual([
      "Injections as written: the guard stops significantly more attacks than Llama Guard 3, Prompt Guard 1 and ProtectAI deberta-v3 v2.",
      "Injections behind an override prefix: the guard stops significantly more attacks than Llama Guard 3; " +
        "ProtectAI deberta-v3 v2 stops significantly more attacks than the guard; no significant difference from Prompt Guard 1.",
      "Benign runs: the guard wrongly blocks significantly fewer than Llama Guard 3 and Prompt Guard 1.",
    ]);
    const voided = Object.fromEntries(Object.entries(study.verdicts).map(([k, v]) => [k, Object.fromEntries(Object.keys(v).map((b) => [b, "void"]))]));
    expect(findings({ guard_vs_detectors: { ...study, verdicts: voided } })).toEqual([]);
  });

  it("shows content safety as Llama Guard's job, whichever way the verdict falls", () => {
    const [g] = resultGroups({ content_safety: content });
    expect(g.id).toBe("content_safety");
    expect(g.note).toMatch(/650 prompts/);
    expect(g.rows.map((r) => r.detail)).toEqual(["250 of 300", "30 of 350", "0 of 300", "1 of 350"]);
    expect(findings({ content_safety: content })).toEqual([
      "On content safety, its own job, Llama Guard 3 flags significantly more unsafe prompts than the guard, which has no rules for it.",
    ]);
    expect(findings({ content_safety: { ...content, verdict: "no_significant_difference" } })[0]).toMatch(/no significant difference/);
    expect(findings({ content_safety: { ...content, verdict: "void" } })).toEqual([]);
  });

  it("matches the committed evidence when the studies are scored", () => {
    const ids = resultGroups(evidence).map((g) => g.id);
    expect(ids.includes("detectors")).toBe(Boolean(evidence.guard_vs_detectors));
    expect(ids.includes("content_safety")).toBe(Boolean(evidence.content_safety));
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
