// Kept out of charts.jsx so that file exports only components (fast refresh).

// A p-value as a reader scans it: p<0.001, p=0.008, p=0.049, p=0.50; with ns, anything >= 0.05 is "n.s.".
export function pShort(p, { ns = false } = {}) {
  if (typeof p !== "number" || !Number.isFinite(p)) return "–";
  if (ns && p >= 0.05) return "n.s.";
  if (p < 0.001) return "p<0.001";
  return `p=${p < 0.1 ? p.toFixed(3) : p.toFixed(2)}`;
}

// Readable experiment names for the prompt-fix tables and panels.
export const EXPERIMENT_NAMES = {
  injecagent: "Tool hijacks (InjecAgent)",
  gandalf: "Password leaks (Gandalf)",
  xstest: "Safe requests refused (XSTest)",
  ifeval: "Instructions missed (IFEval)",
};

// Running offsets for rows of different heights: tops[i] and the total.
export function stack(heights) {
  const tops = [];
  let total = 0;
  for (const h of heights) {
    tops.push(total);
    total += h;
  }
  return { tops, total };
}
