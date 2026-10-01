import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import evidence from "../../content/evidence.json";
import { DiscordantPairs, FixChanges, GraderVsBaselines, GuardTradeoff, StoppedBars } from "./charts";

const img = () => screen.getByRole("img");

describe("Trust charts", () => {
  it("GuardTradeoff plots every system from step 2 with its whiskers and a summary", () => {
    const s = evidence.step2_guard;
    const { container } = render(<GuardTradeoff systems={s.systems} models={s.models} />);
    const label = img().getAttribute("aria-label");
    for (const sys of Object.values(s.systems)) expect(label).toContain(sys.label);
    // two whiskers per system
    expect(container.querySelectorAll("g[stroke] line").length).toBe(2 * Object.keys(s.systems).length);
    expect(screen.getByText("ideal")).toBeInTheDocument();
    expect(container.querySelector("figcaption").textContent).toMatch(/Purple: Fusion/);
  });

  it("StoppedBars shows stopped of attacks per attack type", () => {
    const types = Object.values(evidence.step2_guard.by_attack_type);
    render(<StoppedBars label="By type" rows={types.map((t) => ({ label: t.name, stopped: t.stopped, attacks: t.attacks }))} />);
    for (const t of types) {
      expect(screen.getByText(`${t.stopped} of ${t.attacks}`, { selector: "text" })).toBeInTheDocument();
      expect(img().getAttribute("aria-label")).toContain(t.name);
    }
  });

  it("DiscordantPairs draws both sides of each paired comparison", () => {
    const a = evidence.step3_guard.comparisons.attacks;
    render(
      <DiscordantPairs
        label="Discordant"
        leftLabel="without only"
        rightLabel="with only"
        groups={[{ title: "Attacks stopped", rows: [{ label: "With vs without", left: a.v2_only, right: a.v3_only, p: a.p }] }]}
      />,
    );
    const label = img().getAttribute("aria-label");
    expect(label).toContain(`with only ${a.v3_only}`);
    expect(label).toContain(`without only ${a.v2_only}`);
  });

  it("FixChanges draws one panel per experiment, attacks before costs", () => {
    render(<FixChanges cells={evidence.fix_efficacy} />);
    const experiments = [...new Set(evidence.fix_efficacy.map((c) => c.experiment))];
    const panels = screen.getAllByRole("img");
    expect(panels.length).toBe(experiments.length);
    const kinds = panels.map((p) => /refused|missed/i.test(p.getAttribute("aria-label")));
    expect(kinds).toEqual([...kinds].sort()); // costs (true) come after attacks (false)
    for (const c of evidence.fix_efficacy) expect(screen.getAllByText(c.model).length).toBeGreaterThan(0);
  });

  it("GraderVsBaselines has a key and a row per grader and check", () => {
    const { container } = render(<GraderVsBaselines rows={evidence.judge_accuracy} />);
    expect(screen.getByText("Regex baseline")).toBeInTheDocument();
    expect(img().getAttribute("aria-label")).toContain(evidence.judge_accuracy[0].f1.toFixed(2));
    expect(container.querySelectorAll("svg[role=img] > g > title").length).toBe(evidence.judge_accuracy.length);
  });

  it("renders nothing when the evidence is missing", () => {
    for (const el of [
      <GuardTradeoff key="a" systems={undefined} />,
      <GuardTradeoff key="b" systems={{ fusion: { label: "x" } }} />,
      <StoppedBars key="c" rows={[]} />,
      <StoppedBars key="d" rows={[{ heading: "Only a heading" }]} />,
      <DiscordantPairs key="e" groups={[{ title: "t", rows: [] }]} />,
      <FixChanges key="f" cells={undefined} />,
      <GraderVsBaselines key="g" rows={[]} />,
    ]) {
      const { container, unmount } = render(el);
      expect(container.innerHTML).toBe("");
      unmount();
    }
  });
});
