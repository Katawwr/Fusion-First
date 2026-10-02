import React from "react";
import CopyButton from "../ui/CopyButton";

// Building blocks for the document-style pages; styling lives in index.css (.doc, .data-table, ...).

// Text with `backticks` around code: the code is set inline and the surrounding spaces are kept.
export function Inline({ text }) {
  return String(text || "")
    .split(/(`[^`]+`)/)
    .map((part, i) =>
      part.startsWith("`") && part.endsWith("`") && part.length > 1 ? (
        <code key={i} className="inline-code">
          {part.slice(1, -1)}
        </code>
      ) : (
        part
      ),
    );
}

export function Doc({ wide = false, children }) {
  return <article className={`doc${wide ? " doc--wide" : ""}`}>{children}</article>;
}

export function DocHeader({ title, children }) {
  return (
    <header>
      <h1 className="doc-title">{title}</h1>
      {children && <div className="doc-lead">{children}</div>}
    </header>
  );
}

export function DocSection({ id, title, lead, children }) {
  return (
    <section id={id} className="doc-section" aria-labelledby={id ? `${id}-title` : undefined}>
      <h2 id={id ? `${id}-title` : undefined} className="doc-h2">
        {title}
      </h2>
      {lead && <p className="mt-2 text-[0.95rem] leading-relaxed text-app-muted">{lead}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function DataTable({ head, rows, numeric = [], caption }) {
  return (
    <figure>
      {caption && <figcaption className="fig-caption">{caption}</figcaption>}
      <div className="table-frame">
        <table className="data-table">
          <thead>
            <tr>
              {head.map((h) => (
                <th key={h} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j} className={numeric.includes(j) ? "num" : undefined}>
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

export function Code({ code, label }) {
  return (
    <div className="code-block">
      <div className="flex items-center justify-between gap-3 border-b border-app-border px-3 py-1.5">
        <span className="font-mono text-xs text-app-subtle">{label || ""}</span>
        <CopyButton text={code} label="Copy" />
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

// A forest-plot strip: the 95% interval as a bar, the estimate as a tick. "rate" spans 0–100%;
// "diff" spans −50 to +50 points around zero. Tone: good in purple, costs in pink, comparators in grey.
export function IntervalStrip({ est, scale = "rate", tone = "good", label }) {
  if (!est || est.point === undefined) return null;
  const [lo, hi] = scale === "diff" ? [-0.5, 0.5] : [0, 1];
  const W = 160;
  const x = (v) => 4 + ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (W - 8);
  const color = tone === "cost" ? "var(--pink)" : tone === "neutral" ? "var(--subtle)" : "var(--accent)";
  const ticks = scale === "diff" ? [-0.5, 0, 0.5] : [0, 0.5, 1];
  return (
    <svg
      viewBox={`0 0 ${W} 16`}
      width="100%"
      height="16"
      role="img"
      aria-label={label}
      style={{ display: "block", minWidth: "7rem", maxWidth: "11rem" }}
    >
      <line x1={x(lo)} x2={x(hi)} y1="8" y2="8" stroke="var(--border-strong)" strokeWidth="1" />
      {ticks.map((t) => (
        <line
          key={t}
          x1={x(t)}
          x2={x(t)}
          y1={t === 0 && scale === "diff" ? 1 : 5}
          y2={t === 0 && scale === "diff" ? 15 : 11}
          stroke="var(--border-strong)"
          strokeWidth="1"
        />
      ))}
      <rect
        x={x(est.low)}
        y="5"
        width={Math.max(1.5, x(est.high) - x(est.low))}
        height="6"
        rx="1"
        fill={color}
        opacity="0.35"
      />
      <rect x={x(est.point) - 1.25} y="2" width="2.5" height="12" rx="1" fill={color} />
    </svg>
  );
}
