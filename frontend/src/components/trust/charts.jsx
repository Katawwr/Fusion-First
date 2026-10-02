import React, { useLayoutEffect, useRef, useState } from "react";
import { graderName, pct } from "../../lib/evidence";
import { EXPERIMENT_NAMES, pShort, stack } from "./format";

// Charts for the Trust page. Inline SVG, drawn at the container's pixel width so text stays 12px on a
// phone. Colour: purple (--accent) = Fusion's results, pink (--pink) = costs, grey (--chart-grey) =
// comparators; no other hues. Every chart sits beside the table that holds the same numbers, carries a
// numbered "Figure n." caption below it, and renders nothing when its evidence is missing.

const C = {
  fusion: "var(--accent)",
  cost: "var(--pink)",
  grey: "var(--chart-grey)",
  grid: "var(--border)",
  axis: "var(--border-strong)",
  leader: "var(--subtle)",
  surface: "var(--bg)",
};

const lo = (iv) => iv?.low ?? iv?.ci95?.[0];
const hi = (iv) => iv?.high ?? iv?.ci95?.[1];
const hasRate = (iv) => iv && typeof iv.point === "number";
const textWidth = (s, px = 12) => String(s).length * px * 0.56;
const monoWidth = (s) => String(s).length * 11 * 0.62; // 11px tabular mono
const NARROW = 560;

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

function Figure({ n, caption, note, children }) {
  return (
    <figure className="chart-figure">
      {children}
      {note && <p className="chart-note">{note}</p>}
      {caption && (
        <figcaption>
          {n ? <b>{`Figure ${n}.`}</b> : null}
          {n ? " " : null}
          {caption}
        </figcaption>
      )}
    </figure>
  );
}

function Swatch({ shape = "dot", color }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      {shape === "dot" && <circle cx="7" cy="7" r="5.5" fill={color} />}
      {shape === "ring" && <circle cx="7" cy="7" r="5" fill="none" stroke={color} strokeWidth="2" />}
      {shape === "square" && <rect x="2" y="2" width="10" height="10" fill="none" stroke={color} strokeWidth="2" />}
      {shape === "bar" && <rect x="0" y="3" width="14" height="8" rx="2" fill={color} />}
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

const GUARD_ORDER = ["fusion", "fusion_prior", "union_fusion_b", "llama_guard_b", "llama_guard_a"];
// [wide, narrow]; the narrow forms drop only words the caption restates.
const GUARD_LABEL = {
  fusion: ["Fusion, current rules", "Fusion, current"],
  fusion_prior: ["Fusion, previous rules", "Fusion, previous"],
  llama_guard_a: ["Llama Guard 3, off the shelf", "Llama Guard 3, off the shelf"],
  llama_guard_b: ["Llama Guard 3, configured", "Llama Guard 3, configured"],
  union_fusion_b: ["Fusion + Llama Guard 3, configured", "Fusion + Llama Guard 3"],
};
const GUARD_MARK = {
  fusion: { color: C.fusion, ring: false },
  fusion_prior: { color: C.fusion, ring: true },
  union_fusion_b: { color: C.grey, ring: true },
};

const overlaps = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
const lineBox = (x1, y1, x2, y2, pad = 2) => ({
  x0: Math.min(x1, x2) - pad,
  x1: Math.max(x1, x2) + pad,
  y0: Math.min(y1, y2) - pad,
  y1: Math.max(y1, y2) + pad,
});

// Candidate label boxes around a point: diagonal and side positions, nearest first. A label placed
// beyond the first ring gets a leader line back to its point.
function labelCandidates(cx, cy, w) {
  const h = 13;
  const out = [];
  for (const d of [9, 20, 34]) {
    const a = Math.round(d * 0.75);
    out.push(
      { d, x0: cx + a, y0: cy - a - h }, // NE
      { d, x0: cx + a, y0: cy + a }, // SE
      { d, x0: cx - a - w, y0: cy - a - h }, // NW
      { d, x0: cx - a - w, y0: cy + a }, // SW
      { d, x0: cx - w / 2, y0: cy - d - h }, // N
      { d, x0: cx - w / 2, y0: cy + d }, // S
    );
  }
  return out.map((c) => ({ ...c, x1: c.x0 + w, y1: c.y0 + h }));
}

// x = clean transcripts wrongly blocked, y = attacks stopped; 95% intervals as crosshair whiskers.
export function GuardTradeoff({ systems, models = [], n }) {
  const [ref, width] = useWidth();
  const keys = GUARD_ORDER.filter((k) => hasRate(systems?.[k]?.recall) && hasRate(systems?.[k]?.over_block));
  if (keys.length === 0) return null;
  const narrow = width < NARROW;
  const m = { l: 42, r: 12, t: 24, b: 40 };
  const H = narrow ? 300 : 340;
  const pw = width - m.l - m.r;
  const ph = H - m.t - m.b;
  // Tight domains: x to just past the widest interval, y from the quarter below the lowest one.
  const xMax = Math.max(0.05, Math.max(...keys.map((k) => hi(systems[k].over_block) ?? 0)) + 0.01);
  const yMin = Math.max(0, Math.floor(Math.min(...keys.map((k) => lo(systems[k].recall) ?? 0)) * 4) / 4);
  const xStep = xMax <= 0.3 ? 0.05 : 0.1;
  const xTicks = Array.from({ length: Math.floor(xMax / xStep + 1e-9) + 1 }, (_, i) => i * xStep);
  const yTicks = Array.from({ length: Math.round((1 - yMin) / 0.25) + 1 }, (_, i) => yMin + i * 0.25);
  const x = (v) => m.l + (Math.min(xMax, Math.max(0, v)) / xMax) * pw;
  const y = (v) => m.t + (1 - (Math.min(1, Math.max(yMin, v)) - yMin) / (1 - yMin)) * ph;

  const pts = keys.map((k) => {
    const s = systems[k];
    return {
      k,
      s,
      cx: x(s.over_block.point),
      cy: y(s.recall.point),
      text: (GUARD_LABEL[k] || [s.label, s.label])[narrow ? 1 : 0],
      mark: GUARD_MARK[k] || { color: C.grey, ring: false },
    };
  });

  // Obstacles: the axis titles, the "ideal" marker, every whisker and every point.
  const obstacles = [
    { x0: 0, x1: 120, y0: 0, y1: 16 },
    { x0: m.l, x1: m.l + 50, y0: m.t, y1: m.t + 16 },
    ...pts.flatMap(({ s, cx, cy }) => [
      lineBox(x(lo(s.over_block)), cy, x(hi(s.over_block)), cy),
      lineBox(cx, y(lo(s.recall)), cx, y(hi(s.recall))),
      { x0: cx - 7, x1: cx + 7, y0: cy - 7, y1: cy + 7 },
    ]),
  ];
  const inside = (b) => b.x0 >= m.l + 2 && b.x1 <= width && b.y0 >= 0 && b.y1 <= m.t + ph - 2;
  const labels = pts.map((p) => {
    const w = textWidth(p.text);
    const cands = labelCandidates(p.cx, p.cy, w).filter(inside);
    const hits = (b) => obstacles.filter((o) => overlaps(o, b)).length;
    const best = cands.find((b) => hits(b) === 0) || [...cands].sort((a, b) => hits(a) - hits(b) || a.d - b.d)[0];
    const box = best || { d: 9, x0: p.cx + 7, y0: p.cy - 20, x1: p.cx + 7 + w, y1: p.cy - 7 };
    obstacles.push(box);
    // Leader from the point's edge to the nearest point of the label box.
    let leader = null;
    if (box.d > 9) {
      const nx = Math.min(box.x1, Math.max(box.x0, p.cx));
      const ny = Math.min(box.y1, Math.max(box.y0, p.cy));
      const len = Math.hypot(nx - p.cx, ny - p.cy);
      if (len > 9) leader = { x1: p.cx + ((nx - p.cx) / len) * 7, y1: p.cy + ((ny - p.cy) / len) * 7, x2: nx, y2: ny };
    }
    return { ...p, box, leader };
  });

  const summary = pts
    .map(({ s }) => `${s.label}: ${pct(s.recall.point)} of attacks stopped, ${pct(s.over_block.point)} of clean wrongly blocked`)
    .join("; ");
  return (
    <Figure
      n={n}
      caption={`Attacks stopped against clean transcripts wrongly blocked, one point per guard on the same transcripts${models.length ? ` (${models.join(", ")})` : ""}; whiskers are 95% intervals. Purple: Fusion (filled: current rules; ring: previous). Grey: Llama Guard 3 (ring: union with Fusion, configured).`}
    >
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`Guard trade-off. ${summary}.`}>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={m.l} x2={m.l + pw} y1={y(t)} y2={y(t)} stroke={t === yMin ? C.axis : C.grid} strokeWidth="1" />
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
          <text x={m.l + pw} y={m.t + ph + 31} textAnchor="end">
            Clean transcripts wrongly blocked →
          </text>
          <text x={0} y={12}>
            ↑ Attacks stopped
          </text>
          <path d={`M${m.l + 1},${m.t + 12}V${m.t + 1}H${m.l + 12}`} fill="none" stroke="var(--muted)" strokeWidth="1" />
          <text x={m.l + 15} y={m.t + 12}>
            ideal
          </text>
          {pts.map(({ k, s, cx, cy, mark }) => (
            <g key={k} className="whisker" stroke={mark.color} strokeWidth="1.25">
              <line x1={x(lo(s.over_block))} x2={x(hi(s.over_block))} y1={cy} y2={cy} />
              <line x1={cx} x2={cx} y1={y(lo(s.recall))} y2={y(hi(s.recall))} />
            </g>
          ))}
          {labels.map(({ k, leader }) =>
            leader ? (
              <line key={`ld${k}`} x1={leader.x1} y1={leader.y1} x2={leader.x2} y2={leader.y2} stroke={C.leader} strokeWidth="1" />
            ) : null,
          )}
          {pts.map(({ k, s, cx, cy, mark }) => (
            <g key={`p${k}`}>
              <title>{`${s.label}: stopped ${s.stopped} of ${s.attacks} (${pct(lo(s.recall))}–${pct(hi(s.recall))}); wrongly blocked ${s.blocked} of ${s.clean} (${pct(lo(s.over_block))}–${pct(hi(s.over_block))})`}</title>
              <circle cx={cx} cy={cy} r="12" fill="transparent" />
              <circle
                cx={cx}
                cy={cy}
                r={mark.ring ? 4.5 : 5.5}
                fill={mark.ring ? C.surface : mark.color}
                stroke={mark.ring ? mark.color : C.surface}
                strokeWidth="2"
              />
            </g>
          ))}
          {labels.map(({ k, text, box }) => (
            <text key={`l${k}`} className={k === "fusion" ? "lead" : undefined} x={box.x0} y={box.y1 - 3}>
              {text}
            </text>
          ))}
        </svg>
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 2. stopped bars ------------- */

// rows: [{ label, stopped, attacks, tone: "fusion" | "grey" }] or { heading } separators. The outline is
// every attack; the fill is the share stopped. Rows with no attacks are left out, and a heading with no
// rows under it goes with them.
export function StoppedBars({ rows, caption, note, n, label = "Attacks stopped" }) {
  const [ref, width] = useWidth();
  const valid = (rows || []).filter((r) => r && (r.heading || (r.attacks > 0 && typeof r.stopped === "number")));
  const data = valid.filter((r, i) => !r.heading || (valid[i + 1] && !valid[i + 1].heading));
  if (!data.some((r) => !r.heading)) return null;
  const narrow = width < NARROW;
  const bars = data.filter((r) => !r.heading);
  const valueW = Math.max(...bars.map((r) => monoWidth(`${r.attacks} of ${r.attacks}`))) + 12;
  const labelW = narrow ? 0 : Math.min(Math.max(...bars.map((r) => textWidth(r.label))) + 16, width * 0.42);
  const trackX = labelW;
  const trackW = width - labelW - valueW;
  const BAR = 12;
  const rowH = (r) => (r.heading ? 26 : narrow ? 40 : 28);
  const { tops, total: H } = stack(data.map(rowH));
  const layout = data.map((r, i) => ({ ...r, top: tops[i] }));
  const summary = bars.map((r) => `${r.label}: ${r.stopped} of ${r.attacks}`).join("; ");
  return (
    <Figure n={n} caption={caption} note={note}>
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${label}. ${summary}.`}>
          {layout.map((r, i) => {
            if (r.heading)
              return (
                <text key={i} className="lead strong" x={0} y={r.top + 17}>
                  {r.heading}
                </text>
              );
            const by = narrow ? r.top + 20 : r.top + (28 - BAR) / 2;
            return (
              <g key={i}>
                <title>{`${r.label}: stopped ${r.stopped} of ${r.attacks}, missed ${r.attacks - r.stopped}`}</title>
                <rect x={0} y={r.top} width={width} height={rowH(r)} fill="transparent" />
                <text x={0} y={narrow ? r.top + 13 : by + 10}>
                  {r.label}
                </text>
                <rect x={trackX + 0.5} y={by + 0.5} width={trackW - 1} height={BAR - 1} rx="3" fill="none" stroke={C.axis} strokeWidth="1" />
                <path d={barPath(trackX, trackX + (r.stopped / r.attacks) * trackW, by, BAR)} fill={r.tone === "grey" ? C.grey : C.fusion} />
                <text className="num" x={trackX + trackW + 8} y={by + 10}>
                  {`${r.stopped} of ${r.attacks}`}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </Figure>
  );
}

/* ---------------------------------------------------------------- 3. discordant pairs ---------- */

// Paired McNemar comparisons use only the transcripts the two systems disagree on. groups:
// [{ title, rows: [{ label, left, right, p, tone: "fusion" | "cost" }] }]; left = comparator only (grey),
// right = Fusion only (tone). One shared scale; counts sit at the bar ends, the p-value right after.
export function DiscordantPairs({ groups, leftLabel, rightLabel, caption, n, label = "Discordant pairs" }) {
  const [ref, width] = useWidth();
  const gs = (groups || [])
    .map((g) => ({ ...g, rows: (g.rows || []).filter((r) => Number.isFinite(r.left) && Number.isFinite(r.right)) }))
    .filter((g) => g.rows.length);
  if (gs.length === 0) return null;
  const narrow = width < NARROW;
  const all = gs.flatMap((g) => g.rows);
  const max = Math.max(1, ...all.flatMap((r) => [r.left, r.right]));
  const pW = 64;
  const labelW = narrow ? 0 : Math.min(Math.max(...all.map((r) => textWidth(r.label))) + 16, width * 0.38);
  const areaW = Math.min(380, width - labelW - pW);
  const mid = labelW + areaW / 2;
  const half = areaW / 2 - 28; // room for the count at each bar end
  const BAR = 12;
  const ROW = narrow ? 40 : 28;
  const HEAD = 22;
  const GT = 26;
  const { tops, total } = stack(gs.map((g) => GT + g.rows.length * ROW + 6));
  const layout = gs.map((g, gi) => {
    const top = HEAD + tops[gi];
    return { ...g, top, rows: g.rows.map((r, i) => ({ ...r, top: top + GT + i * ROW })) };
  });
  const H = HEAD + total;
  const summary = gs
    .map((g) => `${g.title}: ${g.rows.map((r) => `${r.label}, ${rightLabel} ${r.right}, ${leftLabel} ${r.left}${typeof r.p === "number" ? `, ${pShort(r.p, { ns: true })}` : ""}`).join("; ")}`)
    .join(". ");
  return (
    <Figure n={n} caption={caption}>
      <div ref={ref}>
        <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${label}. ${summary}.`}>
          <text x={mid - 8} y={13} textAnchor="end">
            {`← ${leftLabel}`}
          </text>
          <text x={mid + 8} y={13}>
            {`${rightLabel} →`}
          </text>
          <text x={labelW + areaW + 8} y={13}>
            McNemar
          </text>
          {layout.map((g) => (
            <g key={g.title}>
              <text className="lead strong" x={0} y={g.top + 17}>
                {g.title}
              </text>
              {g.rows.map((r) => {
                const wl = (r.left / max) * half;
                const wr = (r.right / max) * half;
                const by = narrow ? r.top + 21 : r.top + (ROW - BAR) / 2;
                const ty = by + 10;
                return (
                  <g key={r.label}>
                    <title>{`${r.label}: ${rightLabel} ${r.right}, ${leftLabel} ${r.left}${typeof r.p === "number" ? `, McNemar ${pShort(r.p)}` : ""}`}</title>
                    <rect x={0} y={r.top} width={width} height={ROW} fill="transparent" />
                    <text x={0} y={narrow ? r.top + 13 : ty}>
                      {r.label}
                    </text>
                    <line x1={mid} x2={mid} y1={narrow ? by - 4 : r.top} y2={narrow ? by + BAR + 4 : r.top + ROW} stroke={C.axis} strokeWidth="1" />
                    <path d={barPath(mid - wl, mid - 1, by, BAR, "left")} fill={C.grey} />
                    <path d={barPath(mid + 1, mid + wr, by, BAR, "right")} fill={r.tone === "cost" ? C.cost : C.fusion} />
                    <text className="num" x={mid - wl - 5} y={ty} textAnchor="end">
                      {r.left}
                    </text>
                    <text className="num" x={mid + wr + 5} y={ty}>
                      {r.right}
                    </text>
                    {typeof r.p === "number" && (
                      <text className="num" x={labelW + areaW + 8} y={ty}>
                        {pShort(r.p, { ns: true })}
                      </text>
                    )}
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

const FIX_TITLES = EXPERIMENT_NAMES;
const isCost = (c) => c.kind === "quality";

function FixPanel({ title, cells, cost }) {
  const [ref, width] = useWidth(300);
  const lw = Math.min(104, Math.max(...cells.map((c) => textWidth(c.model))) + 12);
  const m = { l: lw, r: 12 };
  const pw = width - m.l - m.r;
  const x = (v) => m.l + Math.min(1, Math.max(0, v)) * pw;
  const ROW = 30;
  const top = 26;
  const H = top + cells.length * ROW + 20;
  const tone = cost ? C.cost : C.fusion;
  const summary = cells
    .map((c) => `${c.model}: as written ${pct(c.baseline_rate.point)}, with fix ${pct(c.hardened_rate.point)}`)
    .join("; ");
  return (
    <div ref={ref}>
      <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`${title}. ${summary}.`}>
        <text className="lead strong" x={0} y={14}>
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
              <line x1={x(lo(b))} x2={x(hi(b))} y1={cy - 5} y2={cy - 5} stroke={C.grey} strokeWidth="1.25" />
              <line x1={x(lo(h))} x2={x(hi(h))} y1={cy + 5} y2={cy + 5} stroke={tone} strokeWidth="1.25" />
              <circle cx={x(b.point)} cy={cy} r="5" fill={C.grey} stroke={C.surface} strokeWidth="2" />
              <circle cx={x(h.point)} cy={cy} r="5" fill={tone} stroke={C.surface} strokeWidth="2" />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function FixChanges({ cells, n }) {
  const valid = (cells || []).filter((c) => hasRate(c.baseline_rate) && hasRate(c.hardened_rate));
  if (valid.length === 0) return null;
  const experiments = [...new Set(valid.map((c) => c.experiment))];
  const ordered = [
    ...experiments.filter((e) => !valid.some((c) => c.experiment === e && isCost(c))),
    ...experiments.filter((e) => valid.some((c) => c.experiment === e && isCost(c))),
  ];
  return (
    <Figure
      n={n}
      caption="Rate per model as written (grey) and with the fix (purple: attacks that landed; pink: costs); thin lines are 95% intervals. Lower is better in every panel."
    >
      <div className="chart-grid">
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
const shortGrader = (g, narrow) => {
  const s = graderName(String(g));
  return narrow && s.length > 16 ? s.split(/[ ,]/)[0] : s;
};

// A dot plot: one row per grader, grouped under its check. Purple dot = the grader's F1; grey ring and
// square = the rule-based baselines on the same transcripts. No span joins them: they are separate scores.
export function GraderVsBaselines({ rows, checkNames = {}, n, floor }) {
  const [ref, width] = useWidth();
  const data = (rows || []).filter((r) => typeof r.f1 === "number");
  if (data.length === 0) return null;
  const narrow = width < NARROW;
  const fmt = (v) => v.toFixed(2);
  const checks = [...new Set(data.map((r) => r.check))];
  const ROW = 32;
  const GT = 26;
  const valueW = 44;
  const labelW = Math.min(Math.max(...data.map((r) => textWidth(shortGrader(r.grader, narrow)))) + 16, width * 0.4);
  const m = { l: labelW + 8, r: valueW + 8 };
  const pw = width - m.l - m.r;
  const x = (v) => m.l + Math.min(1, Math.max(0, v)) * pw;
  const byCheck = checks.map((c) => data.filter((r) => r.check === c));
  const { tops, total } = stack(byCheck.map((rs) => GT + rs.length * ROW));
  const groups = checks.map((c, ci) => {
    const top = tops[ci];
    const rs = byCheck[ci];
    const bottom = top + GT + rs.length * ROW;
    return { check: c, top, bottom, rows: rs.map((r, i) => ({ ...r, cy: top + GT + i * ROW + ROW / 2 })) };
  });
  const plotB = total + 4;
  const H = plotB + 18;
  const ticks = [0, 0.5, 1];
  const hasFloor = typeof floor === "number" && floor > 0 && floor < 1;
  const line = (r) =>
    `${checkNames[r.check] || r.check}, ${shortGrader(r.grader)}: grader ${fmt(r.f1)}` +
    BASELINES.filter((b) => r.baselines?.[b.key]).map((b) => `, ${b.label.toLowerCase()} ${fmt(r.baselines[b.key].f1)}`).join("");
  const summary = data.map(line).join("; ");
  return (
    <Figure
      n={n}
      caption={`F1 against oracle labels on the same transcripts, point estimates. Purple dot: the grader (value at right). Grey ring: regex baseline; grey square: tuned heuristic.${hasFloor ? ` Dashed line: the policy floor, F1 ${fmt(floor)}.` : ""} Significance tests are listed under the table.`}
    >
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
              {groups.map((g) => (
                <line key={g.check} x1={x(t)} x2={x(t)} y1={g.top + GT - 4} y2={g.bottom + (g.bottom === total ? 4 : 0)} stroke={t === 0 ? C.axis : C.grid} strokeWidth="1" />
              ))}
              <text className="num" x={x(t)} y={H - 4} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}>
                {fmt(t)}
              </text>
            </g>
          ))}
          {hasFloor && (
            <g className="floor">
              {groups.map((g) => (
                <line key={g.check} x1={x(floor)} x2={x(floor)} y1={g.top + GT - 4} y2={g.bottom} stroke="var(--muted)" strokeWidth="1" strokeDasharray="3 3" />
              ))}
              <text x={x(floor) + 4} y={H - 4}>
                floor
              </text>
            </g>
          )}
          <text className="num" x={width} y={H - 4} textAnchor="end">
            F1
          </text>
          {groups.map((g) => (
            <g key={g.check}>
              <text className="lead strong" x={0} y={g.top + 17}>
                {checkNames[g.check] || g.check}
              </text>
              {g.rows.map((r) => (
                <g key={`${r.check}-${r.grader}`}>
                  <title>{line(r)}</title>
                  <rect x={0} y={r.cy - ROW / 2} width={width} height={ROW} fill="transparent" />
                  <text x={0} y={r.cy + 4}>
                    {shortGrader(r.grader, narrow)}
                  </text>
                  <line x1={x(0)} x2={x(1)} y1={r.cy} y2={r.cy} stroke={C.grid} strokeWidth="1" />
                  {BASELINES.map((b) => {
                    const v = r.baselines?.[b.key]?.f1;
                    if (typeof v !== "number") return null;
                    return b.shape === "ring" ? (
                      <circle key={b.key} cx={x(v)} cy={r.cy} r="5" fill={C.surface} stroke={C.grey} strokeWidth="2" />
                    ) : (
                      <rect key={b.key} x={x(v) - 5} y={r.cy - 5} width="10" height="10" fill={C.surface} stroke={C.grey} strokeWidth="2" />
                    );
                  })}
                  <circle cx={x(r.f1)} cy={r.cy} r="6" fill={C.fusion} stroke={C.surface} strokeWidth="2" />
                  <text className="num lead" x={width} y={r.cy + 4} textAnchor="end">
                    {fmt(r.f1)}
                  </text>
                </g>
              ))}
            </g>
          ))}
        </svg>
      </div>
    </Figure>
  );
}
