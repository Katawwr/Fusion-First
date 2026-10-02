import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import Trust, { Step2Section, Step3Section, Step4Section } from "./Trust";
import { EXPERIMENT_NAMES } from "../components/trust/format";
import { fixVerdict, graderName, interval, pct, significanceByGrader } from "../lib/evidence";
import evidence from "../content/evidence.json";

const renderTrust = () =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <Trust />
      </MemoryRouter>
    </HelmetProvider>,
  );

describe("Trust page", () => {
  it("names the page in the browser tab", async () => {
    renderTrust();
    await waitFor(() => expect(document.title).toBe("How far to trust Fusion | Fusion First"));
  });

  it("formats both interval shapes", () => {
    expect(pct(0.925)).toBe("93%");
    expect(interval({ point: 0.8, low: 0.68, high: 0.88 })).toBe("80% (68%–88%)");
    expect(interval({ point: 0.05, ci95: [0.022, 0.112] })).toBe("5% (2%–11%)");
    expect(interval(null)).toBe("–");
  });

  it("shows the guardrail's results before the prompt fix's", () => {
    renderTrust();
    const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    const guard = titles.findIndex((t) => /\bguard\b/i.test(t));
    expect(guard).toBeGreaterThan(-1);
    expect(guard).toBeLessThan(titles.indexOf("Prompt fix: effect and cost"));
  });

  it("charts the evidence beside its tables", () => {
    renderTrust();
    const labels = screen.getAllByRole("img").map((el) => el.getAttribute("aria-label") || "");
    if (evidence.step2_guard) expect(labels.some((l) => l.startsWith("Guard trade-off"))).toBe(true);
    if (evidence.step3_guard) expect(labels.some((l) => l.startsWith("Attacks stopped with and without the tool results"))).toBe(true);
    if (evidence.judge_accuracy?.length) expect(labels.some((l) => l.startsWith("F1 of grader"))).toBe(true);
    for (const l of labels) expect(l.length).toBeGreaterThan(10);
  });

  it("numbers every figure in page order, with the caption below the chart", () => {
    const { container } = renderTrust();
    const caps = [...container.querySelectorAll("figure.chart-figure > figcaption")];
    expect(caps.length).toBeGreaterThan(0);
    caps.forEach((c, i) => expect(c.textContent.startsWith(`Figure ${i + 1}. `)).toBe(true));
    for (const c of caps) expect(c.previousElementSibling).not.toBeNull(); // the chart comes first
  });

  it("renders only what the evidence contains, and says what isn't measured", () => {
    renderTrust();
    expect(screen.getByRole("heading", { name: "How far to trust Fusion" })).toBeInTheDocument();
    if (!evidence.fix_efficacy) {
      expect(screen.getByText(/Not yet measured: the as-written vs fixed prompt/)).toBeInTheDocument();
    }
    for (const j of evidence.judge_accuracy) {
      expect(screen.getAllByText(interval(j.accuracy)).length).toBeGreaterThan(0);
    }
  });

  it("says whether the rubric beats a plain judge, and shows the fix pooled over models", () => {
    renderTrust();
    const rvp = evidence.rubric_vs_plain;
    if (rvp) {
      expect(screen.getByRole("heading", { name: /Rubric grading vs one plain question/ })).toBeInTheDocument();
      expect(screen.getAllByText(interval(rvp.pooled.plain)).length).toBeGreaterThan(0);
      if (!rvp.claim_allowed) expect(screen.getByText("Rubric grading is no more accurate than one plain question to the grader.")).toBeInTheDocument();
    }
    for (const s of significanceByGrader(evidence.judge_accuracy)) {
      expect(screen.getByText(s)).toBeInTheDocument(); // direction stated per grader
    }
    for (const p of evidence.fix_pooled || []) {
      const name = EXPERIMENT_NAMES[p.experiment] || p.experiment;
      expect(screen.getAllByRole("cell", { name: `${name}, all models` }).length).toBe(1);
    }
  });

  it("shows only current results: no superseded guard measurements, no per-attack-type bars", () => {
    renderTrust();
    const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    for (const t of titles) expect(t).not.toMatch(/previous rules|value ledger|vs Llama Guard 3 \(/i);
    const labels = screen.getAllByRole("img").map((el) => el.getAttribute("aria-label") || "");
    expect(labels.some((l) => /by attack type/i.test(l))).toBe(false);
    expect(screen.queryByText(/SUPERSEDED/)).toBeNull();
    expect(screen.getByText(/Held-out tool calls, scored once\. Defense/)).toBeInTheDocument();
    expect(screen.queryByText(/scored once \(rules/)).toBeNull();
    expect(evidence.guard_heldout.length).toBeLessThanOrEqual(1);
  });

  it("marks a grader below the policy floor and says its pre-registered bar is not met", () => {
    renderTrust();
    const lg = evidence.local_grader;
    if (!lg) return;
    for (const j of evidence.judge_accuracy.filter((r) => r.grader === lg.grader && lg.per_check[r.check]?.meets === false)) {
      expect(screen.getAllByRole("cell", { name: `${graderName(j.grader)} (below the floor)` }).length).toBeGreaterThan(0);
    }
    if (!lg.meets_floor) expect(screen.getByText(/below the policy floor .* not recommended/)).toBeInTheDocument();
  });

  it("shows the current rules against the previous rules and Llama Guard, with the registered decisions", () => {
    const sys = (label, stopped, blocked) => ({
      label, attacks: 148, stopped, clean: 252, blocked,
      recall: { point: stopped / 148, low: 0, high: 1 }, over_block: { point: blocked / 252, low: 0, high: 1 },
    });
    const s = {
      models: ["qwen2.5:7b", "llama3.1:8b"], rules: "0c560b5", prior_rules: "a6fa0f5",
      systems: {
        fusion: sys("Fusion guard, current rules", 132, 2),
        fusion_prior: sys("Fusion guardrail, previous rules", 104, 0),
        llama_guard_a: sys("Llama Guard 3, off the shelf", 58, 30),
        llama_guard_b: sys("Llama Guard 3, configured", 77, 24),
        union_fusion_b: sys("Fusion + Llama Guard 3 (configured)", 145, 25),
      },
      comparisons: {
        previous_rules: { decision: "fusion_better", attacks: { mcnemar_p: 7.45e-9 } },
        off_the_shelf: { decision: "fusion_better", attacks: { mcnemar_p: 1.3e-14 } },
        configured: { decision: "fusion_better", attacks: { mcnemar_p: 0.02 } },
      },
      benign_heldout: { cases: 20, blocked: 1, max_allowed: 2 },
      findings: ["The external-recipient rule, unchanged and with no allowlist, blocked 12 of the 20 (every send)."],
    };
    render(<Step2Section s={s} />);
    expect(screen.getByText(/every tool call that is not a read must be covered by the user's own request/)).toBeInTheDocument();
    expect(screen.getByText(/external-recipient rule, unchanged and with no allowlist, blocked 12 of 20/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Request-bound guard on qwen2.5:7b and llama3.1:8b/ })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Fusion guardrail, previous rules" })).toBeInTheDocument();
    expect(screen.getByText(/Previous rules: the current rules stop significantly more .*p<0.001/)).toBeInTheDocument();
    expect(screen.getByText(/Llama Guard 3 configured: .*p=0.020\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 20 blocked \(registered limit 2\)/)).toBeInTheDocument();
  });

  it("shows the guard with and without the tool results from the committed evidence", () => {
    render(<Step3Section s={evidence.step3_guard} />);
    expect(screen.getByRole("heading", { name: /The guard given the tool results/ })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /^75 of 75/ })).toBeInTheDocument();
    const a = evidence.step3_guard.comparisons.attacks;
    const note = document.querySelector(".chart-note").textContent;
    expect(note).toContain(`${a.v3_only} attacks stopped only with the tool results, ${a.v2_only} only without (p=0.008)`);
    expect(screen.getByText(/Decision: adopted\. Attack wording was seen in development/)).toBeInTheDocument();
  });

  it("names a significant regression instead of calling it inconclusive", () => {
    const worse = { before_after: { absolute_reduction: { point: -0.23 }, mcnemar_p: 0.039, honesty: "INCONCLUSIVE" } };
    const noisy = { before_after: { absolute_reduction: { point: -0.17 }, mcnemar_p: 0.125, honesty: "INCONCLUSIVE" } };
    const proven = { before_after: { absolute_reduction: { point: 0.4 }, mcnemar_p: 0.001, honesty: "PROVEN" } };
    expect(fixVerdict(worse).text).toMatch(/Significantly worse/);
    expect(fixVerdict(noisy).text).toMatch(/not significant/);
    expect(fixVerdict(proven).text).toMatch(/Significantly better/);
  });

  it("states the guard's cost in a live agent loop with its registered decision", () => {
    const s = evidence.step4_agentdojo;
    render(<Step4Section s={s} />);
    expect(screen.getByRole("heading", { name: /cost in a live agent loop/ })).toBeInTheDocument();
    const u = s.utility_benign;
    expect(screen.getByText(new RegExp(`^${u.none.k} of ${u.none.n}`))).toBeInTheDocument();
    expect(screen.getByText(s.comparisons.cost_none_vs_v3.non_inferior ? /within the margin/ : /over the margin/)).toBeInTheDocument();
  });
});
