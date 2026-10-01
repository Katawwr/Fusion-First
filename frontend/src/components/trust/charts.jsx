import React, { useLayoutEffect, useRef, useState } from "react";
import { pct, pValue } from "../../lib/evidence";

// Charts for the Trust page. Inline SVG, drawn at the container's pixel width so text stays 12px on a
// phone. Colour: purple (--accent) = Fusion's results, pink (--pink) = costs, grey (--chart-grey) =
// comparators. Every chart sits beside the table that holds the same numbers; each renders nothing
// when its evidence is missing.

const C = {
  fusion: "var(--accent)",
  cost: "var(--pink)",
  grey: "var(--chart-grey)",
  grid: "var(--border)",
  axis: "var(--border-strong)",
  surface: "var(--bg)",
};

const lo = (iv) => iv?.low ?? iv?.ci95?.[0];
const hi = (iv) => iv?.high ?? iv?.ci95?.[1];
const hasRate = (iv) => iv && typeof iv.point === "number";
const textWidth = (s, px = 12) => s.length * px * 0.56;

// Width of the wrapping element; ResizeObserver reports it on observe and on every resize. Falls back to
// a desktop width where there is no layout (tests, SSR).
function useWidth(fallback = 640) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

// A bar with a 4px rounded data end and a square baseline end.
function barPath(x0, x1, y, h, end = "right", r = 4) {
  const w = x1 - x0;
  if (w <= 0) return "";
  const rr = Math.min(r, w, h / 2);
  if (end === "right")
    return `M${x0},${y}H${x1 - rr}Q${x1},${y} ${x1},${y + rr}V${y + h - rr}Q${x1},${y + h} ${x1 - rr},${y + h}H${x0}Z`;
  return `M${x1},${y}H${x0 + rr}Q${x0},${y} ${x0},${y + rr}V${y + h - rr}Q${x0},${y + h} ${x0 + rr},${y + h}H${x1}Z`;
}

function Figure({ caption, children, className = "" }) {
  return (
    <figure className={`chart-figure ${className}`}>
      {children}
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}

function Swatch({ shape = "dot", color }) {
  return (
    <svg width="12" height="12" aria-hidden="true">
      {shape === "dot" && <circle cx="6" cy="6" r="4.5" fill={color} />}
      {shape === "ring" && <circle cx="6" cy="6" r="4" fill="none" stroke={color} strokeWidth="2" />}
      {shape === "square" && <rect x="2" y="2" width="8" height="8" fill="none" stroke={color} strokeWidth="2" />}
      {shape === "bar" && <rect x="0" y="3" width="12" height="6" rx="1.5" fill={color} />}
    </svg>
  );
}

function Key({ items }) {
  return (
    <div className="chart-key" aria-hidden="true">
      {items.map((it) => (
        <span key={it.label}>
          <Swatch shape={it.shape} color={it.color} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- 1. guard trade-off scatter -- */

const GUARD_ORDER = ["fusion", "fusion_prior", "llama_guard_a", "llama_guard_b", "union_fusion_b"];
const GUARD_SHORT = {
  fusion: "Fusion",
  fusion_prior: "Fusion, previous",
  llama_guard_a: "Llama Guard 3",
  llama_guard_b: "LG3 configured",
  union_fusion_b: "Fusion + LG3",
};
const GUARD_MARK = {
  fusion: { color: C.fusion, ring: false },
  fusion_prior: { color: C.fusion, ring: true },
  union_fusion_b: { color: C.grey, ring: true },
};

const overlaps = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

// x = clean conversations wrongly blocked, y = attacks stopped; 95% intervals as crosshair whiskers.
export function GuardTradeoff({ systems, models = [] }) {
  const [ref, width] = useWidth();
  const keys = GUARD_ORDER.filter((k) => hasRate(systems?.[k]?.recall) && hasRate(systems?.[k]?.over_block));
  if (keys.length === 0) return null;
  const narrow = width < 480;
  const m = { l: 40, r: 12, t: 26, b: 40 };
  const H = narrow ? 300 : 330;
  const pw = width - m.l - m.r;
  const ph = H - m.t - m.b;
  const xMax = Math.max(0.05, Math.ceil(Math.max(...keys.map((k) => hi(systems[k].over_block) ?? 0)) * 20) / 20);
  const xStep = xMax <= 0.25 ? 0.05 : 0.1;
  const xTicks = Array.from({ length: Math.round(xMax / xStep) + 1 }, (_, i) => i * xStep);
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const x = (v) => m.l + (Math.min(xMax, Math.max(0, v)) / xMax) * pw;
  const y = (v) => m.t + (1 - Math.min(1, Math.max(0, v))) * ph;

  // Direct labels: first candidate position that clears the plot edge and earlier labels.
  const ideal = { x0: m.l + 2, x1: m.l + 44, y0: m.t + 1, y1: m.t + 15 };
  const placed = [ideal];
  const points = keys.map((k) => {
    const s = systems[k];
    const cx = x(s.over_block.point);
    const cy = y(s.recall.point);
    const text = narrow ? GUARD_SHORT[k] || s.label : s.label;
    const w = textWidth(text);
    const candidates = [
      [cx + 8, cy - 8],
      [cx + 8, cy + 16],
      [cx - 8 - w, cy - 8],
      [cx - 8 - w, cy + 16],
    ];
    let pos = candidates[0];
    for (const [tx, ty] of candidates) {
      const box = { x0: tx, x1: tx + w, y0: ty - 11, y1: ty + 2 };
      if (tx >= m.l && tx + w <= width && ty - 11 >= 0 && !placed.some((b) => overlaps(b, box))) {
        pos = [tx, ty];
        break;
      }
    }
    placed.push({ x0: pos[0], x1: pos[0] + w, y0: pos[1] - 11, y1: pos[1] + 2 });
    return { k, s, cx, cy, text, tx: pos[0], ty: pos[1], mark: GUARD_MARK[k] || { color: C.grey, ring: false } };
  });

  const summary = points
    .map(({ s }) => `${s.label}: ${pct(s.recall.point)} of attacks stopped, ${pct(s.over_block.point)} of clean wrongly blocked`)
    .join("; ");
  return (
    <Figure
      caption={`One point per guard on the same transcripts${models.length ? ` (${models.join(", ")})` : ""}. Whiskers: 95% intervals. Purple: Fusion (filled: current rules; ring: previous). Grey: Llama Guard 3 (ring: union with Fusion).`}
    >
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`Guard trade-off. ${summary}.`}>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={m.l} x2={m.l + pw} y1={y(t)} y2={y(t)} stroke={t === 0 ? C.axis : C.grid} strokeWidth="1" />
              <text className="num" x={m.l - 6} y={y(t) + 4} textAnchor="end">
                {pct(t)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <g key={`x${t}`}>
              <line x1={x(t)} x2={x(t)} y1={m.t} y2={m.t + ph} stroke={t === 0 ? C.axis : C.grid} strokeWidth="1" />
              <text className="num" x={x(t)} y={m.t + ph + 15} textAnchor="middle">
                {pct(t)}
              </text>
            </g>
          ))}
          <text x={m.l + pw} y={H - 4} textAnchor="end">
            Clean conversations wrongly blocked →
          </text>
          <text x={0} y={12}>
            ↑ Attacks stopped
          </text>
          <path d={`M${m.l + 1},${m.t + 12}V${m.t + 1}H${m.l + 12}`} fill="none" stroke="var(--muted)" strokeWidth="1" />
          <text x={m.l + 15} y={m.t + 12}>
            ideal
          </text>
          {points.map(({ k, s, cx, cy, mark }) => (
            <g key={k} stroke={mark.color} strokeWidth="1">
              <line x1={x(lo(s.over_block))} x2={x(hi(s.over_block))} y1={cy} y2={cy} />
              <line x1={cx} x2={cx} y1={y(lo(s.recall))} y2={y(hi(s.recall))} />
            </g>
          ))}
          {points.map(({ k, s, cx, cy, mark }) => (
            <g key={`p${k}`}>
              <title>{`${s.label}: stopped ${s.stopped} of ${s.attacks} (${pct(lo(s.recall))}–${pct(hi(s.recall))}); wrongly blocked ${s.blocked} of ${s.clean} (${pct(lo(s.over_block))}–${pct(hi(s.over_block))})`}</title>
              <circle cx={cx} cy={cy} r="12" fill="transparent" />
              <circle
                cx={cx}
                cy={cy}
                r={mark.ring ? 4.5 : 5}
                fill={mark.ring ? C.surface : mark.color}
                stroke={mark.ring ? mark.color : C.surface}
                strokeWidth="2"
              />
            </g>
          ))}
          {points.map(({ k, text, tx, ty }) => (
            <text key={`l${k}`} className={k === "fusion" ? "lead" : undefined} x={tx} y={ty}>
              {text}
            </text>
          ))}
        </svg>
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 2. stopped vs missed bars ---- */

// rows: [{ label, stopped, attacks, tone: "fusion" | "grey" }] or { heading } separators. The outline is
// every attack; the fill is the share stopped.
export function StoppedBars({ rows, caption, label = "Attacks stopped" }) {
  const [ref, width] = useWidth();
  const data = (rows || []).filter((r) => r.heading || (r.attacks > 0 && typeof r.stopped === "number"));
  if (!data.some((r) => !r.heading)) return null;
  const BAR = 10;
  const heights = data.map((r) => (r.heading ? 22 : 40));
  const layout = data.map((r, i) => ({ ...r, top: heights.slice(0, i).reduce((t, h) => t + h, 0) }));
  const H = heights.reduce((t, h) => t + h, 0);
  const summary = data
    .filter((r) => !r.heading)
    .map((r) => `${r.label}: ${r.stopped} of ${r.attacks}`)
    .join("; ");
  return (
    <Figure caption={caption}>
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${label}. ${summary}.`}>
          {layout.map((r, i) =>
            r.heading ? (
              <text key={i} className="lead" x={0} y={r.top + 15} style={{ fontWeight: 600 }}>
                {r.heading}
              </text>
            ) : (
              <g key={i}>
                <title>{`${r.label}: stopped ${r.stopped} of ${r.attacks}, missed ${r.attacks - r.stopped}`}</title>
                <text x={0} y={r.top + 13}>
                  {r.label}
                </text>
                <text className="num" x={width} y={r.top + 13} textAnchor="end">
                  {`${r.stopped} of ${r.attacks}`}
                </text>
                <rect
                  x={0.5}
                  y={r.top + 19.5}
                  width={width - 1}
                  height={BAR - 1}
                  rx="2"
                  fill="none"
                  stroke={C.axis}
                  strokeWidth="1"
                />
                <path
                  d={barPath(0, (r.stopped / r.attacks) * width, r.top + 19, BAR)}
                  fill={r.tone === "grey" ? C.grey : C.fusion}
                />
              </g>
            ),
          )}
        </svg>
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 3. discordant pairs ---------- */

// Paired McNemar comparisons use only the transcripts the two systems disagree on. groups:
// [{ title, rows: [{ label, left, right, p, tone: "fusion" | "cost" }] }]; left = comparator only (grey),
// right = Fusion only (tone).
export function DiscordantPairs({ groups, leftLabel, rightLabel, caption, label = "Discordant pairs" }) {
  const [ref, width] = useWidth();
  const gs = (groups || [])
    .map((g) => ({ ...g, rows: (g.rows || []).filter((r) => Number.isFinite(r.left) && Number.isFinite(r.right)) }))
    .filter((g) => g.rows.length);
  if (gs.length === 0) return null;
  const max = Math.max(1, ...gs.flatMap((g) => g.rows.flatMap((r) => [r.left, r.right])));
  const pad = 30;
  const mid = width / 2;
  const half = mid - pad;
  const BAR = 12;
  const gh = gs.map((g) => 22 + g.rows.length * 40 + 4);
  const layout = gs.map((g, gi) => {
    const top = 18 + gh.slice(0, gi).reduce((t, h) => t + h, 0);
    return { ...g, top, rows: g.rows.map((r, i) => ({ ...r, top: top + 22 + i * 40 })) };
  });
  const H = 18 + gh.reduce((t, h) => t + h, 0);
  const summary = gs
    .map((g) => `${g.title}: ${g.rows.map((r) => `${r.label}, ${rightLabel} ${r.right}, ${leftLabel} ${r.left}`).join("; ")}`)
    .join(". ");
  return (
    <Figure caption={caption}>
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${label}. ${summary}.`}>
          <text x={mid - 8} y={11} textAnchor="end">
            {`← ${leftLabel}`}
          </text>
          <text x={mid + 8} y={11}>
            {`${rightLabel} →`}
          </text>
          <line x1={mid} x2={mid} y1={16} y2={H} stroke={C.axis} strokeWidth="1" />
          {layout.map((g) => (
            <g key={g.title}>
              <text className="lead" x={0} y={g.top + 15} style={{ fontWeight: 600 }}>
                {g.title}
              </text>
              {g.rows.map((r) => {
                const wl = (r.left / max) * half;
                const wr = (r.right / max) * half;
                const by = r.top + 18;
                return (
                  <g key={r.label}>
                    <title>{`${r.label}: ${rightLabel} ${r.right}, ${leftLabel} ${r.left}${typeof r.p === "number" ? `, McNemar ${pValue(r.p)}` : ""}`}</title>
                    <text x={0} y={r.top + 12}>
                      {r.label}
                    </text>
                    {typeof r.p === "number" && (
                      <text className="num" x={width} y={r.top + 12} textAnchor="end">
                        {pValue(r.p)}
                      </text>
                    )}
                    <path d={barPath(mid - wl, mid - 1, by, BAR, "left")} fill={C.grey} />
                    <path d={barPath(mid + 1, mid + wr, by, BAR, "right")} fill={r.tone === "cost" ? C.cost : C.fusion} />
                    <text className="num" x={mid - wl - 5} y={by + 10} textAnchor="end">
                      {r.left}
                    </text>
                    <text className="num" x={mid + wr + 5} y={by + 10}>
                      {r.right}
                    </text>
                  </g>
                );
              })}
            </g>
          ))}
        </svg>
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 4. prompt fix per model ------ */

const FIX_TITLES = {
  injecagent: "Tool hijacks that landed (InjecAgent)",
  gandalf: "Password leaks (Gandalf)",
  xstest: "Safe requests refused (XSTest)",
  ifeval: "Instructions missed (IFEval)",
};
const isCost = (c) => c.kind === "quality";

function FixPanel({ title, cells, cost }) {
  const [ref, width] = useWidth(300);
  const lw = Math.min(96, Math.round(width * 0.3));
  const m = { l: lw, r: 10 };
  const pw = width - m.l - m.r;
  const x = (v) => m.l + Math.min(1, Math.max(0, v)) * pw;
  const ROW = 28;
  const top = 22;
  const H = top + cells.length * ROW + 20;
  const tone = cost ? C.cost : C.fusion;
  const summary = cells
    .map((c) => `${c.model}: as written ${pct(c.baseline_rate.point)}, with fix ${pct(c.hardened_rate.point)}`)
    .join("; ");
  return (
    <div ref={ref}>
      <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${title}. ${summary}.`}>
        <text className="lead" x={0} y={13} style={{ fontWeight: 600 }}>
          {title}
        </text>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={H - 18} stroke={t === 0 ? C.axis : C.grid} strokeWidth="1" />
            <text className="num" x={x(t)} y={H - 5} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}>
              {pct(t)}
            </text>
          </g>
        ))}
        {cells.map((c, i) => {
          const cy = top + i * ROW + ROW / 2;
          const b = c.baseline_rate;
          const h = c.hardened_rate;
          return (
            <g key={c.model}>
              <title>{`${c.model}: as written ${pct(b.point)} (${pct(lo(b))}–${pct(hi(b))}), with fix ${pct(h.point)} (${pct(lo(h))}–${pct(hi(h))}), ${c.n_paired} pairs`}</title>
              <rect x={0} y={cy - ROW / 2} width={width} height={ROW} fill="transparent" />
              <text x={0} y={cy + 4}>
                {c.model}
              </text>
              <line x1={x(lo(b))} x2={x(hi(b))} y1={cy - 4} y2={cy - 4} stroke={C.grey} strokeWidth="1" />
              <line x1={x(lo(h))} x2={x(hi(h))} y1={cy + 4} y2={cy + 4} stroke={tone} strokeWidth="1" />
              <line x1={x(b.point)} x2={x(h.point)} y1={cy} y2={cy} stroke="var(--subtle)" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx={x(b.point)} cy={cy} r="4.5" fill={C.grey} stroke={C.surface} strokeWidth="2" />
              <circle cx={x(h.point)} cy={cy} r="4.5" fill={tone} stroke={C.surface} strokeWidth="2" />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function FixChanges({ cells }) {
  const valid = (cells || []).filter((c) => hasRate(c.baseline_rate) && hasRate(c.hardened_rate));
  if (valid.length === 0) return null;
  const experiments = [...new Set(valid.map((c) => c.experiment))];
  const ordered = [...experiments.filter((e) => !valid.some((c) => c.experiment === e && isCost(c))),
    ...experiments.filter((e) => valid.some((c) => c.experiment === e && isCost(c)))];
  return (
    <Figure caption="Rate per model, as written (grey) and with the fix (purple: attacks that landed; pink: costs). Thin lines: 95% intervals. Lower is better in every panel.">
      <div className="chart-grid chart-grid--2">
        {ordered.map((e) => {
          const cs = valid.filter((c) => c.experiment === e);
          return <FixPanel key={e} title={FIX_TITLES[e] || e} cells={cs} cost={cs.some(isCost)} />;
        })}
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 5. grader vs baselines ------- */

const BASELINES = [
  { key: "naive_regex", label: "Regex baseline", shape: "ring" },
  { key: "tuned_heuristic", label: "Tuned heuristic", shape: "square" },
];
const shortGrader = (g) => String(g).split(" (")[0];

export function GraderVsBaselines({ rows, checkNames = {} }) {
  const [ref, width] = useWidth();
  const data = (rows || []).filter((r) => typeof r.f1 === "number");
  if (data.length === 0) return null;
  const ROW = 42;
  const m = { l: 6, r: 10 };
  const pw = width - m.l - m.r;
  const x = (v) => m.l + Math.min(1, Math.max(0, v)) * pw;
  const H = data.length * ROW + 20;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const fmt = (v) => v.toFixed(2);
  const summary = data
    .map(
      (r) =>
        `${checkNames[r.check] || r.check}, ${shortGrader(r.grader)}: grader ${fmt(r.f1)}` +
        BASELINES.filter((b) => r.baselines?.[b.key]).map((b) => `, ${b.label.toLowerCase()} ${fmt(r.baselines[b.key].f1)}`).join(""),
    )
    .join("; ");
  return (
    <Figure caption="F1 against oracle labels, same transcripts. Purple: the grader. Grey: rule-based baselines. Point estimates; the significance tests are listed under the table.">
      <Key
        items={[
          { label: "Grader", shape: "dot", color: C.fusion },
          ...BASELINES.map((b) => ({ label: b.label, shape: b.shape, color: C.grey })),
        ]}
      />
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`F1 of grader vs rule-based baselines. ${summary}.`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={0} y2={H - 18} stroke={t === 0 ? C.axis : C.grid} strokeWidth="1" />
              <text className="num" x={x(t)} y={H - 5} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}>
                {fmt(t)}
              </text>
            </g>
          ))}
          {data.map((r, i) => {
            const top = i * ROW;
            const cy = top + 28;
            const vals = [r.f1, ...BASELINES.map((b) => r.baselines?.[b.key]?.f1).filter((v) => typeof v === "number")];
            return (
              <g key={`${r.check}-${r.grader}`}>
                <title>{summary.split("; ")[i]}</title>
                <rect x={0} y={top} width={width} height={ROW} fill="transparent" />
                <text x={m.l} y={top + 13}>
                  {`${checkNames[r.check] || r.check} · ${shortGrader(r.grader)}`}
                </text>
                <line x1={x(Math.min(...vals))} x2={x(Math.max(...vals))} y1={cy} y2={cy} stroke="var(--muted)" strokeWidth="1" />
                {BASELINES.map((b) => {
                  const v = r.baselines?.[b.key]?.f1;
                  if (typeof v !== "number") return null;
                  return b.shape === "ring" ? (
                    <circle key={b.key} cx={x(v)} cy={cy} r="4.5" fill={C.surface} stroke={C.grey} strokeWidth="2" />
                  ) : (
                    <rect key={b.key} x={x(v) - 4} y={cy - 4} width="8" height="8" fill={C.surface} stroke={C.grey} strokeWidth="2" />
                  );
                })}
                <circle cx={x(r.f1)} cy={cy} r="5" fill={C.fusion} stroke={C.surface} strokeWidth="2" />
              </g>
            );
          })}
        </svg>
      </div>
    </Figure>
  );
}
