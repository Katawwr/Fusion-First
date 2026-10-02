"""Render SafetyReportCards as one self-contained HTML report (pure functions, every field escaped,
no external assets)."""

from __future__ import annotations

import html

from fusion_first.engine.guard_replay import in_sample_payload
from fusion_first.guardrail.snippet import guardrail_snippet
from fusion_first.schemas import Honesty, ProbeOutcome, SafetyReportCard

# The prompt fix's measured caveat (Trust Report: fix efficacy on small open-weight models).
FIX_CAVEAT = ("On the small open-weight models measured, the prompt fix rarely cut attacks and raised "
              "refusals of safe requests. Re-test it on your model before you ship it.")

_GRADE_TONE = {"A": "ok", "B": "ok", "C": "warn", "D": "warn", "F": "bad", "?": "muted"}
_HONESTY_TONE = {Honesty.PROVEN: "ok", Honesty.PRELIMINARY: "warn", Honesty.INCONCLUSIVE: "muted"}

# The FF mark (frontend/public/ff.svg): 10x10 pixel grid, one row per string.
_FF_ROWS = ("##########", "##########", "##...##...", "##...##...", "#########.",
            "#########.", "##........", "##...##...", "##...##...", "##...##...")


def _esc(s: object) -> str:
    return html.escape(str(s))


def _mark(size: int = 28) -> str:
    cells = "".join(f"M{14 + 3.6 * x:.1f} {14 + 3.6 * y:.1f}h3.6v3.6h-3.6z"
                    for y, row in enumerate(_FF_ROWS) for x, c in enumerate(row) if c == "#")
    return (f'<svg class="mark" width="{size}" height="{size}" viewBox="0 0 64 64" aria-hidden="true">'
            f'<rect width="64" height="64" rx="14" fill="#504d9a"/>'
            f'<path fill="#fff" shape-rendering="crispEdges" d="{cells}"/></svg>')


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _title(check: str) -> str:
    return check.replace("_", " ").capitalize()


def _delta_text(point: float) -> str:
    """Never a double negative: a regression is named as one."""
    if point > 0:
        return f"{point*100:.0f}% lower issue rate with the fix"
    if point < 0:
        return f"{-point*100:.0f}% higher issue rate with the fix (regression)"
    return "Issue rate unchanged by the fix"


def _judge_notes(card: SafetyReportCard) -> str:
    """Why a grade is withheld (or accuracy unmeasured), and how independent the grader is."""
    out = ""
    if card.judge_accuracy_note:
        out += f'<p class="note">{_esc(card.judge_accuracy_note)}</p>'
    if card.trust.independence_disclosure:
        out += (f'<p class="note">Grader independence: {_esc(card.trust.independence or "unknown")}. '
                f'{_esc(card.trust.independence_disclosure)}</p>')
    return out


def _accuracy(card: SafetyReportCard) -> str:
    a = card.judge_accuracy
    if not a:
        if not (card.judge_accuracy_note or card.trust.independence_disclosure):
            return ""
        return f'<div class="panel"><h3>Grader accuracy</h3>{_judge_notes(card)}</div>'
    return f"""<div class="panel"><h3>Grader accuracy</h3>
          <dl class="stats">
            <div><dt>Precision</dt><dd>{_pct(a.precision.point)}</dd></div>
            <div><dt>Recall</dt><dd>{_pct(a.recall.point)}</dd></div>
            <div><dt>Kappa</dt><dd>{a.cohen_kappa:.2f}</dd></div>
          </dl>
          <p class="fine">{a.n} known-answer cases. Precision {_pct(a.precision.low)}–{_pct(a.precision.high)}, 95% CI.</p>
          {_judge_notes(card)}</div>"""


def _fix_result(card: SafetyReportCard) -> str:
    d = card.before_after
    if not d:
        return ""
    worse = d.hardened_issue_rate > d.baseline_issue_rate
    rows = "".join(
        f'<div class="bar"><span>{label}</span><span class="track"><i class="{tone}" '
        f'style="width:{round(rate * 100)}%"></i></span><b>{_pct(rate)}</b></div>'
        for label, rate, tone in (("As written", d.baseline_issue_rate, "grey"),
                                  ("With fix", d.hardened_issue_rate, "pink" if worse else "purple")))
    r = d.absolute_reduction
    return f"""<div class="panel"><h3>Prompt fix, re-tested</h3>
          {rows}
          <p class="delta">{_esc(_delta_text(r.point))}</p>
          <p class="fine">95% CI {r.low*100:.0f} to {r.high*100:.0f} pts · McNemar p={d.mcnemar_p:.3f} · {d.n_pairs} pairs</p></div>"""


def _fix_block(card: SafetyReportCard, idx: int) -> str:
    if not card.fix_snippet:
        return ""
    fid = f"fix{idx}"
    cmd = f"fusion harden --prompt your_prompt.txt --check {card.check}"
    return f"""<details class="fix"><summary>Optional: prompt fix · {_esc(card.fix_title)}</summary>
          <div class="codehead"><code>{_esc(cmd)}</code>
            <button class="copy" type="button" onclick="fusionCopy('{fid}', this)">Copy</button></div>
          <pre id="{fid}" class="code">{_esc(card.fix_snippet)}</pre></details>"""


def render_report_card_html(card: SafetyReportCard, idx: int = 0) -> str:
    gtone = _GRADE_TONE.get(card.grade, "muted")
    codes = " · ".join(_esc(x) for t in card.owasp_tags for x in (t.llm, t.asi) if x)
    pill = ""
    if card.before_after:
        tone = _HONESTY_TONE.get(card.before_after.honesty, "muted")
        pill = f'<span class="pill {tone}">{card.before_after.honesty.value}</span>'
    return f"""
      <section class="card" id="{_esc(card.check)}">
        <header class="card-h">
          <span class="grade {gtone}">{_esc(card.grade)}</span>
          <h2>{_esc(_title(card.check))}</h2>
          <span class="codes">{codes}</span>{pill}
        </header>
        <div class="panels">{_accuracy(card)}{_fix_result(card)}</div>
        {_fix_block(card, idx)}
        <footer class="prov">judge {_esc(card.judge_model)} · gold {_esc(card.gold_version)} · crosswalk {_esc(card.crosswalk_version)} · verify {_esc(card.verification_hash)}</footer>
      </section>"""


def render_guard_html(cards: list[SafetyReportCard], outcomes: list[ProbeOutcome] | None = None) -> str:
    """The guardrail code for the safety checks graded here; empty for a quality-only report."""
    checks = [c.check for c in cards if c.kind == "safety"]
    if not checks:
        return ""
    replay = in_sample_payload(outcomes or [], cards)
    replay_html = f'<p class="note">{_esc(replay["sentence"])} {_esc(replay["setup"])}</p>' if replay else ""
    return f"""
      <section class="guard">
        <div class="section-h"><h2>Runtime guardrail</h2>
          <button class="copy" type="button" onclick="fusionCopy('guard', this)">Copy</button></div>
        <p class="lede">Redacts leaked secrets and blocks tool calls the user's request does not cover.</p>
        {replay_html}
        <pre id="guard" class="code">{_esc(guardrail_snippet(checks))}</pre>
      </section>"""


def render_overview_html(cards: list[SafetyReportCard]) -> str:
    tiles = "".join(
        f'<a class="tile" href="#{_esc(c.check)}"><span class="grade {_GRADE_TONE.get(c.grade, "muted")}">'
        f'{_esc(c.grade)}</span><span>{_esc(_title(c.check))}</span></a>'
        for c in cards)
    return f'<nav class="summary" aria-label="Checks">{tiles}</nav>'


_DARK = """--bg:#131419;--surface:#1b1c23;--surface-2:#24262f;--border:rgba(255,255,255,.09);
  --text:#eceef2;--muted:#a2a7b5;--subtle:#7c8190;--accent:#8b86d6;--accent-ink:#aba7ea;
  --accent-soft:rgba(139,134,214,.14);--pink:#e98aa6;--grey:#656a76;--ok:#6cc79a;--warn:#e2b45f;--bad:#e88a8a;"""
_LIGHT = """--bg:#f7f8fa;--surface:#ffffff;--surface-2:#f0f1f5;--border:rgba(16,20,36,.1);
  --text:#15161c;--muted:#575d6b;--subtle:#868c9a;--accent:#504d9a;--accent-ink:#4a4791;
  --accent-soft:rgba(80,77,154,.08);--pink:#cf2f7d;--grey:#a3a8b3;--ok:#1f9d63;--warn:#a9761b;--bad:#cf4b4b;"""

_CSS = f"""
:root{{{_DARK}
  --serif:"Newsreader","Iowan Old Style",Georgia,serif;
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace}}
@media (prefers-color-scheme:light){{:root:not([data-theme="dark"]){{{_LIGHT}}}}}
:root[data-theme="dark"]{{{_DARK}}}
:root[data-theme="light"]{{{_LIGHT}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}}
.wrap{{max-width:880px;margin:0 auto;padding:40px 20px 72px}}
.masthead{{display:flex;align-items:center;gap:12px;padding-bottom:20px;border-bottom:1px solid var(--border)}}
.brand{{font:600 19px/1 var(--serif);letter-spacing:-.01em}}
.target{{margin-left:auto;color:var(--muted);font-size:13px}}
.tag{{font:600 11px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--accent-ink);
  background:var(--accent-soft);border-radius:999px;padding:6px 10px}}
h1{{font:500 30px/1.15 var(--serif);letter-spacing:-.01em;margin:28px 0 16px}}
h2{{margin:0;font:600 16px/1.3 var(--sans)}}
h3{{margin:0 0 10px;font:600 11px/1 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--subtle)}}
.summary{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:28px}}
.tile{{display:flex;align-items:center;gap:10px;padding:8px 12px 8px 8px;border:1px solid var(--border);
  border-radius:10px;background:var(--surface);color:var(--text);text-decoration:none;font-size:14px}}
.tile:hover{{border-color:var(--accent)}}
.tile .grade{{width:28px;height:28px;font-size:14px;border-radius:7px}}
.guard,.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px;margin-bottom:16px}}
.section-h{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.lede{{margin:0 0 12px;color:var(--muted);font-size:14px}}
.note{{margin:8px 0 0;color:var(--muted);font-size:13px}}
.caveat{{margin:24px 0 12px;color:var(--subtle);font-size:13px}}
.card-h{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.grade{{width:36px;height:36px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;
  font:600 18px/1 var(--sans);flex:none;border:1px solid currentColor}}
.grade.ok{{color:var(--ok)}} .grade.warn{{color:var(--warn)}} .grade.bad{{color:var(--bad)}} .grade.muted{{color:var(--muted)}}
.codes{{font:500 11px/1 var(--mono);color:var(--subtle);letter-spacing:.04em}}
.pill{{margin-left:auto;font:600 10.5px/1 var(--sans);letter-spacing:.08em;border-radius:999px;padding:6px 10px}}
.pill.ok{{color:var(--ok);background:color-mix(in srgb,var(--ok) 14%,transparent)}}
.pill.warn{{color:var(--warn);background:color-mix(in srgb,var(--warn) 14%,transparent)}}
.pill.muted{{color:var(--muted);background:var(--surface-2)}}
.panels{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:16px}}
.panel{{background:var(--surface-2);border-radius:10px;padding:14px 16px}}
.stats{{display:flex;gap:28px;margin:0}}
.stats div{{display:flex;flex-direction:column-reverse;gap:4px}}
.stats dt{{font-size:12px;color:var(--muted)}}
.stats dd{{margin:0;font:600 22px/1 var(--mono);font-variant-numeric:tabular-nums}}
.fine{{margin:10px 0 0;font-size:12px;color:var(--subtle)}}
.bar{{display:grid;grid-template-columns:76px 1fr 44px;align-items:center;gap:10px;font-size:13px;color:var(--muted);margin-bottom:8px}}
.bar b{{text-align:right;color:var(--text);font:600 13px/1 var(--mono)}}
.track{{height:8px;border-radius:999px;background:var(--bg);overflow:hidden}}
.track i{{display:block;height:100%;border-radius:999px;min-width:6px}}
.track i.grey{{background:var(--grey)}} .track i.purple{{background:var(--accent)}} .track i.pink{{background:var(--pink)}}
.delta{{margin:12px 0 0;font-weight:600;font-size:14px}}
.fix{{margin-top:12px;border-top:1px solid var(--border);padding-top:12px}}
.fix summary{{cursor:pointer;font-size:13px;color:var(--muted)}}
.fix summary:hover{{color:var(--text)}}
.codehead{{display:flex;align-items:center;gap:10px;margin:12px 0 8px}}
.codehead code{{font:12px/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}}
.copy{{margin-left:auto;font:600 12px/1 var(--sans);color:var(--accent-ink);background:transparent;cursor:pointer;
  border:1px solid var(--accent);border-radius:8px;padding:6px 12px}}
.copy:hover{{background:var(--accent-soft)}}
.copy:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.code{{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;
  font:12px/1.6 var(--mono);color:var(--text);white-space:pre-wrap;overflow-x:auto}}
.prov{{margin-top:14px;font:10.5px/1.5 var(--mono);color:var(--subtle);overflow-wrap:anywhere}}
@media (max-width:560px){{.stats{{gap:18px}}.target{{display:none}}}}
"""

_JS = """
function fusionCopy(id, btn){
  var el=document.getElementById(id); if(!el) return;
  var text=el.innerText;
  function done(){btn.textContent='Copied'; setTimeout(function(){btn.textContent='Copy';},1400);}
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(done).catch(function(){select(el);});
  } else { select(el); }
  function select(node){var r=document.createRange();r.selectNodeContents(node);
    var s=window.getSelection();s.removeAllRanges();s.addRange(r);
    try{document.execCommand('copy');done();}catch(e){}}
}
"""


def render_dashboard_html(cards: list[SafetyReportCard], title: str = "Safety Report",
                          outcomes: list[ProbeOutcome] | None = None, theme: str | None = None) -> str:
    """The report page. A scan's `outcomes` add its in-sample guard replay to the guardrail block.
    `theme` ("dark" | "light") pins the theme the site had selected; otherwise the reader's system decides."""
    theme_attr = f' data-theme="{theme}"' if theme in ("dark", "light") else ""
    body = "".join(render_report_card_html(c, i) for i, c in enumerate(cards))
    demo = any(c.demonstration for c in cards)
    caveat = f'<p class="caveat">{_esc(FIX_CAVEAT)}</p>' if any(c.fix_snippet for c in cards) else ""
    return f"""<!doctype html><html lang="en"{theme_attr}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fusion First: {_esc(title)}</title><style>{_CSS}</style></head>
<body>
  <div class="wrap">
    <header class="masthead">{_mark()}<span class="brand">Fusion First</span>
      {'<span class="tag">Example Report</span>' if demo else ""}<span class="target">{_esc(title)}</span></header>
    <h1>Safety report card</h1>
    {render_overview_html(cards)}
    {render_guard_html(cards, outcomes)}
    {caveat}
    {body}
  </div>
  <script>{_JS}</script>
</body></html>"""
