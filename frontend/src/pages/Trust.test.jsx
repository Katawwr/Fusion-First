import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Trust, { GuardrailSection } from "./Trust";
import { fixVerdict, interval, pct, significanceByGrader } from "../lib/evidence";
import evidence from "../content/evidence.json";

describe("Trust page", () => {
  it("formats both interval shapes", () => {
    expect(pct(0.925)).toBe("93%");
    expect(interval({ point: 0.8, low: 0.68, high: 0.88 })).toBe("80% (68%–88%)");
    expect(interval({ point: 0.05, ci95: [0.022, 0.112] })).toBe("5% (2%–11%)");
    expect(interval(null)).toBe("—");
  });

  it("renders only what the evidence contains, and says what isn't measured", () => {
    render(
      <MemoryRouter>
        <Trust />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "How far to trust Fusion" })).toBeInTheDocument();
    if (!evidence.fix_efficacy) {
      expect(screen.getByText(/Not yet measured: the as-written vs fixed prompt/)).toBeInTheDocument();
    }
    for (const j of evidence.judge_accuracy) {
      expect(screen.getAllByText(interval(j.accuracy)).length).toBeGreaterThan(0);
    }
  });

  it("says whether the rubric beats a plain judge, and shows the fix pooled over models", () => {
    render(
      <MemoryRouter>
        <Trust />
      </MemoryRouter>,
    );
    const rvp = evidence.rubric_vs_plain;
    if (rvp) {
      expect(screen.getByRole("heading", { name: /Rubric judge vs a plain question/ })).toBeInTheDocument();
      expect(screen.getAllByText(interval(rvp.pooled.plain)).length).toBeGreaterThan(0);
      if (!rvp.claim_allowed) expect(screen.getByText(/not more accurate than a plain question/)).toBeInTheDocument();
    }
    if (evidence.runtime_guardrail) {
      expect(screen.getByRole("heading", { name: /runtime guardrail on real attacks/i })).toBeInTheDocument();
      expect(screen.getAllByText(interval(evidence.runtime_guardrail.all.recall)).length).toBeGreaterThan(0);
    }
    if (evidence.value_ledger) {
      expect(screen.getByRole("heading", { name: /value ledger/i })).toBeInTheDocument();
      expect(screen.getByRole("cell", { name: "All models" })).toBeInTheDocument();
      // the ledger re-reads the first run, even when a fresh guardrail number is the headline above it
      expect(screen.getByText(/First-run transcripts, item by item/)).toBeInTheDocument();
    }
    for (const s of significanceByGrader(evidence.judge_accuracy)) {
      expect(screen.getByText(s)).toBeInTheDocument(); // direction stated per grader
    }
    for (const p of evidence.fix_pooled || []) {
      expect(screen.getAllByText(new RegExp(`^${p.experiment} \\(all models\\)$`)).length).toBe(1);
    }
  });

  it("says which guardrail measurement it shows, and keeps the first one disclosed", () => {
    const s = (attacks, stopped, clean, over) => ({
      attacks, stopped, clean, over_blocked: over,
      recall: { point: stopped / attacks, low: 0, high: 1 },
      over_block: { point: over / clean, low: 0, high: 1 },
    });
    const first = { all: s(69, 54, 171, 9), by_attack_type: { "gandalf:leak": { ...s(35, 34, 85, 0), name: "leaks" } } };
    const { rerender } = render(
      <GuardrailSection runtime={{ models: ["a", "b"], fresh: false, findings: [], first_measurement: null, ...first }} />,
    );
    expect(screen.getByText(/successful attacks on 2 small open-weight models/)).toBeInTheDocument();
    rerender(
      <GuardrailSection
        runtime={{
          models: ["a", "b", "c", "d"], fresh: true, findings: ["A plain finding."],
          all: s(60, 50, 180, 4), by_attack_type: { "gandalf:leak": { ...s(30, 29, 90, 0), name: "leaks" } },
          first_measurement: { evidence: "x.json", ...first },
        }}
      />,
    );
    expect(screen.getByText(/fresh transcripts/)).toBeInTheDocument();
    expect(screen.getByText(/First measurement \(older rules\): 54 of 69 stopped/)).toBeInTheDocument();
    expect(screen.getByText("A plain finding.")).toBeInTheDocument();
    expect(screen.queryByText(/mixed-case names/)).toBeNull(); // a bug since fixed isn't described as current
  });

  it("names a significant regression instead of calling it inconclusive", () => {
    const worse = { before_after: { absolute_reduction: { point: -0.23 }, mcnemar_p: 0.039, honesty: "INCONCLUSIVE" } };
    const noisy = { before_after: { absolute_reduction: { point: -0.17 }, mcnemar_p: 0.125, honesty: "INCONCLUSIVE" } };
    const proven = { before_after: { absolute_reduction: { point: 0.4 }, mcnemar_p: 0.001, honesty: "PROVEN" } };
    expect(fixVerdict(worse).text).toMatch(/Significantly worse/);
    expect(fixVerdict(noisy).text).toMatch(/not significant/);
    expect(fixVerdict(proven).text).toMatch(/Significantly better/);
  });
});
