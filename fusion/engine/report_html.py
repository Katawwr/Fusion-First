"""Render a SafetyReportCard as self-contained, brand-styled HTML — the customer-facing artifact.

Uses the fixed Fusion palette (purple/cyan/pink) and severity scale. Pure functions returning HTML
strings; no external assets, so a card can be emailed, embedded, or shared as a single file. A
DEMONSTRATION card is visibly banded so it can never be mistaken for a real efficacy claim.
"""

from __future__ import annotations

import html

from fusion.schemas import Honesty, SafetyReportCard

# Fixed brand tokens (must match frontend/tailwind.config.cjs — brand is preserved).
PURPLE = "#504d9a"
CYAN = "#66c4e1"
PINK = "#f38f95"
DARK_PINK = "#db418b"
GRADE_COLORS = {"A": "#22c55e", "B": "#66c4e1", "C": "#facc15", "D": "#fb923c", "F": "#ef4444", "?": "#94a3b8"}
HONESTY_COLORS = {
    Honesty.PROVEN: "#22c55e",
    Honesty.PRELIMINARY: "#facc15",
    Honesty.INCONCLUSIVE: "#94a3b8",
}


def _esc(s: str) -> str:
    return html.escape(str(s))


def _bar(baseline: float, hardened: float) -> str:
    b = round(baseline * 100)
    h = round(hardened * 100)
    return f"""
    <div class="ba">
      <div class="ba-row"><span class="ba-label">Baseline</span>
        <div class="ba-track"><div class="ba-fill bad" style="width:{b}%"></div></div>
        <span class="ba-val">{b}%</span></div>
      <div class="ba-row"><span class="ba-label">Hardened</span>
        <div class="ba-track"><div class="ba-fill good" style="width:{h}%"></div></div>
        <span class="ba-val">{h}%</span></div>
    </div>"""


def render_report_card_html(card: SafetyReportCard) -> str:
    grade_c = GRADE_COLORS.get(card.grade, GRADE_COLORS["?"])
    tags = " ".join(
        f'<span class="chip">{_esc(t.llm)} · {_esc(t.asi)}</span>'
        for t in card.owasp_tags
        if t.llm
    )
    acc_html = ""
    if card.judge_accuracy:
        a = card.judge_accuracy
        acc_html = f"""
        <div class="stat">
          <div class="stat-title">Judge accuracy <span class="muted">vs {_esc(a.label_source)} · n={a.n}</span></div>
          <div class="metrics">
            <div><b>{a.precision.point*100:.0f}%</b><span>precision<br><span class="ci">CI {a.precision.low*100:.0f}–{a.precision.high*100:.0f}</span></span></div>
            <div><b>{a.recall.point*100:.0f}%</b><span>recall<br><span class="ci">CI {a.recall.low*100:.0f}–{a.recall.high*100:.0f}</span></span></div>
            <div><b>{a.f1:.2f}</b><span>F1</span></div>
            <div><b>{a.cohen_kappa:.2f}</b><span>κ vs oracle</span></div>
          </div>
        </div>"""

    ba_html = ""
    if card.before_after:
        ba = card.before_after
        hc = HONESTY_COLORS.get(ba.honesty, "#94a3b8")
        ba_html = f"""
        <div class="stat">
          <div class="stat-title">Safety improvement
            <span class="badge" style="background:{hc}22;color:{hc};border-color:{hc}55">{ba.honesty.value}</span>
          </div>
          {_bar(ba.baseline_issue_rate, ba.hardened_issue_rate)}
          <div class="reduction">−{ba.absolute_reduction.point*100:.0f}% issue rate
            <span class="ci">(CI {ba.absolute_reduction.low*100:.0f}–{ba.absolute_reduction.high*100:.0f}, McNemar p={ba.mcnemar_p:.3f}, {ba.n_pairs} paired)</span>
          </div>
        </div>"""

    fixes = "".join(f"<li>{_esc(f)}</li>" for f in card.top_fixes)
    fixes_html = f'<div class="fixes"><div class="stat-title">Top fixes</div><ol>{fixes}</ol></div>' if fixes else ""

    demo = ""
    if card.demonstration:
        demo = '<div class="demo">DEMONSTRATION — offline stand-in judge, not a real efficacy claim</div>'

    return f"""
    <section class="card">
      {demo}
      <header class="card-head">
        <div class="grade" style="--gc:{grade_c}">{_esc(card.grade)}</div>
        <div>
          <div class="check">{_esc(card.check.replace('_',' '))}</div>
          <div class="tags">{tags}</div>
        </div>
      </header>
      {acc_html}
      {ba_html}
      {fixes_html}
      <footer class="prov">judge {_esc(card.judge_model)} · gold {_esc(card.gold_version)} · crosswalk {_esc(card.crosswalk_version)} · verify {_esc(card.verification_hash)}</footer>
    </section>"""


_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:linear-gradient(135deg,#504d9a 0%,#66c4e1 50%,#504d9a 100%);color:#0f172a;min-height:100vh;padding:32px 16px}
.wrap{max-width:1100px;margin:0 auto}
.brand{color:#fff;text-align:center;margin-bottom:8px;font-size:30px;font-weight:800;letter-spacing:-.5px}
.brand span{background:linear-gradient(to right,#66c4e1,#f38f95);-webkit-background-clip:text;background-clip:text;color:transparent}
.tagline{color:#e2e8f0;text-align:center;margin-bottom:28px;font-size:15px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}
.card{background:#fff;border-radius:16px;padding:22px;box-shadow:0 10px 40px rgba(0,0,0,.25)}
.demo{background:#fef3c7;color:#92400e;border:1px solid #fcd34d;border-radius:8px;padding:6px 10px;font-size:12px;font-weight:600;margin-bottom:14px}
.card-head{display:flex;gap:16px;align-items:center;margin-bottom:16px}
.grade{width:56px;height:56px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:30px;font-weight:800;color:#fff;background:var(--gc);flex:none}
.check{font-size:19px;font-weight:700;text-transform:capitalize}
.tags{margin-top:4px}
.chip{display:inline-block;background:#eef2ff;color:#504d9a;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;margin-right:6px}
.stat{border-top:1px solid #eef2f7;padding:14px 0}
.stat-title{font-size:13px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.4px;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.muted{font-weight:400;text-transform:none;color:#94a3b8;letter-spacing:0}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.metrics>div{text-align:center;background:#f8fafc;border-radius:10px;padding:10px 4px}
.metrics b{display:block;font-size:22px;color:#504d9a}
.metrics span{font-size:11px;color:#64748b}
.ci{color:#94a3b8;font-size:10px}
.badge{font-size:11px;font-weight:700;border-radius:999px;padding:2px 10px;border:1px solid}
.ba{display:flex;flex-direction:column;gap:8px}
.ba-row{display:flex;align-items:center;gap:10px}
.ba-label{width:70px;font-size:12px;color:#64748b}
.ba-track{flex:1;background:#f1f5f9;border-radius:999px;height:14px;overflow:hidden}
.ba-fill{height:100%;border-radius:999px}
.ba-fill.bad{background:linear-gradient(to right,#f38f95,#ef4444)}
.ba-fill.good{background:linear-gradient(to right,#66c4e1,#22c55e)}
.ba-val{width:40px;text-align:right;font-weight:700;font-size:13px}
.reduction{margin-top:10px;font-weight:700;color:#0f172a}
.fixes{border-top:1px solid #eef2f7;padding-top:14px}
.fixes ol{margin:8px 0 0;padding-left:18px}
.fixes li{font-size:13px;color:#334155;margin-bottom:6px}
.prov{margin-top:14px;font-family:'Courier New',monospace;font-size:10px;color:#94a3b8;word-break:break-all}
.overview{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);border-radius:14px;padding:16px 18px;margin-bottom:22px;backdrop-filter:blur(6px)}
.demo-global{margin-bottom:14px}
.ov-stats{display:flex;flex-wrap:wrap;gap:14px;align-items:center}
.ov{background:rgba(255,255,255,.9);border-radius:10px;padding:10px 16px;text-align:center;min-width:120px}
.ov b{display:block;font-size:26px;color:#504d9a;line-height:1}
.ov span{font-size:11px;color:#64748b}
.ov-wide{flex:1;text-align:left;min-width:220px}
.ov-lbl{display:block;font-size:11px;color:#64748b;margin-bottom:6px;text-transform:uppercase;letter-spacing:.4px}
"""


def render_overview_html(cards: list[SafetyReportCard]) -> str:
    """Summary-before-detail strip: coverage and outcome posture across all checks."""
    codes = sorted({t.asi for c in cards for t in c.owasp_tags if t.asi})
    proven = sum(1 for c in cards if c.before_after and c.before_after.honesty == Honesty.PROVEN)
    prelim = sum(1 for c in cards if c.before_after and c.before_after.honesty == Honesty.PRELIMINARY)
    demo = any(c.demonstration for c in cards)
    demo_banner = (
        '<div class="demo demo-global">These are DEMONSTRATION numbers from an offline stand-in '
        "judge — they validate the methodology, not a real deployment. Supplying a live judge key "
        "and re-recording yields real numbers with no other change.</div>"
        if demo
        else ""
    )
    chips = " ".join(f'<span class="chip">{_esc(x)}</span>' for x in codes)
    return f"""
    <div class="overview">
      {demo_banner}
      <div class="ov-stats">
        <div class="ov"><b>{len(cards)}</b><span>safety checks</span></div>
        <div class="ov"><b>{proven}</b><span>proven improvements</span></div>
        <div class="ov"><b>{prelim}</b><span>preliminary</span></div>
        <div class="ov ov-wide"><span class="ov-lbl">OWASP Agentic coverage</span>{chips}</div>
      </div>
    </div>"""


def render_dashboard_html(cards: list[SafetyReportCard], title: str = "Safety Report") -> str:
    body = "".join(render_report_card_html(c) for c in cards)
    overview = render_overview_html(cards)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fusion First — {_esc(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
  <div class="brand">Fusion <span>First</span></div>
  <div class="tagline">Agentic AI safety, proven — every number carries a confidence interval or an honesty badge.</div>
  {overview}
  <div class="grid">{body}</div>
</div></body></html>"""
