import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import evidence from "../../content/evidence.json";
import { DiscordantPairs, FixChanges, GraderVsBaselines, GuardTradeoff, StoppedBars } from "./charts";
import { pShort } from "./format";

const img = () => screen.getByRole("img");
const num = (el, a) => Number(el.getAttribute(a));
// The charts' own label-width estimate (12px sans).
const textBox = (t) => {
  const x = num(t, "x");
  const y = num(t, "y");
  const w = t.textContent.length * 12 * 0.56;
  return { x0: x, x1: x + w, y0: y - 10, y1: y + 2 };
};
const hit = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

describe("Trust charts", () => {
  it("formats p-values for scanning", () => {
    expect(pShort(1.3e-14)).toBe("p<0.001");
    expect(pShort(0.0078125)).toBe("p=0.008");
    expect(pShort(0.02)).toBe("p=0.020");
    expect(pShort(0.5)).toBe("p=0.50");
    expect(pShort(0.5, { ns: true })).toBe("n.s.");
    expect(pShort(0.049, { ns: true })).toBe("p=0.049");
    expect(pShort(undefined)).toBe("–");
  });

  it("GuardTradeoff plots every system from step 2 with its whiskers and a summary", () => {
    const s = evidence.step2_guard;
    const { container } = render(<GuardTradeoff n={2} systems={s.systems} models={s.models} />);
    const label = img().getAttribute("aria-label");
    for (const sys of Object.values(s.systems)) expect(label).toContain(sys.label);
    // two whiskers per system
    expect(container.querySelectorAll("g.whisker line").length).toBe(2 * Object.keys(s.systems).length);
    expect(screen.getByText("ideal")).toBeInTheDocument();
    const cap = container.querySelector("figcaption").textContent;
    expect(cap.startsWith("Figure 2. ")).toBe(true);
    expect(cap).toMatch(/Purple: Fusion/);
  });

  it("GuardTradeoff places point labels clear of every whisker and of each other", () => {
    const s = evidence.step2_guard;
    const { container } = render(<GuardTradeoff systems={s.systems} models={s.models} />);
    const whiskers = [...container.querySelectorAll("g.whisker line")].map((l) => ({
      x0: Math.min(num(l, "x1"), num(l, "x2")) - 1,
      x1: Math.max(num(l, "x1"), num(l, "x2")) + 1,
      y0: Math.min(num(l, "y1"), num(l, "y2")) - 1,
      y1: Math.max(num(l, "y1"), num(l, "y2")) + 1,
    }));
    const names = ["Fusion, current rules", "Fusion, previous rules", "Llama Guard 3, off the shelf", "Llama Guard 3, configured", "Fusion + Llama Guard 3, configured"];
    const boxes = names.map((n) => textBox(screen.getByText(n, { selector: "text" })));
    boxes.forEach((b, i) => {
      for (const w of whiskers) expect(hit(b, w)).toBe(false);
      boxes.slice(i + 1).forEach((o) => expect(hit(b, o)).toBe(false));
      expect(b.x1).toBeLessThanOrEqual(640);
    });
    // the x domain stops just past the widest interval instead of rounding up to the next tick
    const ticks = [...container.querySelectorAll("text.num")].map((t) => t.textContent);
    expect(ticks).not.toContain("20%");
  });

  it("StoppedBars shows stopped of attacks per attack type, labels beside the bars", () => {
    const types = Object.values(evidence.step2_guard.by_attack_type);
    render(<StoppedBars label="By type" rows={types.map((t) => ({ label: t.name, stopped: t.stopped, attacks: t.attacks }))} />);
    for (const t of types) {
      expect(screen.getByText(`${t.stopped} of ${t.attacks}`, { selector: "text" })).toBeInTheDocument();
      expect(img().getAttribute("aria-label")).toContain(t.name);
    }
  });

  it("StoppedBars hides empty rows and a heading left with nothing under it", () => {
    render(
      <StoppedBars
        label="Arms"
        note="One clear note."
        rows={[{ heading: "All attacks" }, { label: "With", stopped: 5, attacks: 5 }, { heading: "Empty" }, { label: "None", stopped: 0, attacks: 0 }]}
      />,
    );
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.queryByText("None")).toBeNull();
    expect(screen.getByText("One clear note.")).toBeInTheDocument();
  });

  it("DiscordantPairs draws both sides of each paired comparison, p as p<0.001 or n.s.", () => {
    const c = evidence.step2_guard.comparisons;
    render(
      <DiscordantPairs
        label="Discordant"
        leftLabel="other only"
        rightLabel="Fusion only"
        groups={[
          { title: "Attacks stopped", rows: [{ label: "Previous rules", left: c.previous_rules.attacks.other_only, right: c.previous_rules.attacks.fusion_only, p: c.previous_rules.attacks.mcnemar_p }] },
          { title: "Clean", rows: [{ label: "Previous rules", left: c.previous_rules.clean.other_only, right: c.previous_rules.clean.fusion_only, p: c.previous_rules.clean.mcnemar_p, tone: "cost" }] },
        ]}
      />,
    );
    const label = img().getAttribute("aria-label");
    expect(label).toContain(`Fusion only ${c.previous_rules.attacks.fusion_only}`);
    expect(label).toContain(`other only ${c.previous_rules.attacks.other_only}`);
    expect(screen.getByText("p<0.001")).toBeInTheDocument();
    expect(screen.getByText("n.s.")).toBeInTheDocument();
    expect(screen.queryByText(/p=\d\.\d{4}/)).toBeNull();
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

  it("GraderVsBaselines is a dot plot: a key, a row per grader and check, no span between marks", () => {
    const rows = evidence.judge_accuracy;
    const { container } = render(<GraderVsBaselines rows={rows} checkNames={{ direct_prompt_injection: "Prompt injection" }} />);
    expect(screen.getByText("Regex baseline")).toBeInTheDocument();
    expect(img().getAttribute("aria-label")).toContain(rows[0].f1.toFixed(2));
    expect(container.querySelectorAll("svg[role=img] title").length).toBe(rows.length);
    // one heading per check, in a left-column layout
    expect(screen.getAllByText("Prompt injection", { selector: "text" }).length).toBe(1);
    // horizontal lines are full-width guides in the grid colour, never a range between two marks
    const horizontal = [...container.querySelectorAll("svg[role=img] line")].filter((l) => l.getAttribute("y1") === l.getAttribute("y2"));
    expect(horizontal.length).toBe(rows.length);
    for (const l of horizontal) expect(l.getAttribute("stroke")).toBe("var(--border)");
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
