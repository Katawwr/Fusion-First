"""Render a SafetyReportCard as self-contained, professional HTML — the customer-facing artifact.

Clean, information-dense, theme-aware (light/dark), no gradient. The Fusion wordmark and indigo
accent preserve the brand; semantic colors carry state (grade, honesty). Each card ends with a
copy-paste-ready fix block and the exact `fusion harden` command to auto-apply it. Pure functions
returning HTML; all fields are escaped; no external assets.
"""

from __future__ import annotations

import html

from fusion.schemas import Honesty, SafetyReportCard

_GRADE_TONE = {"A": "good", "B": "good", "C": "warn", "D": "warn", "F": "bad", "?": "muted"}
_HONESTY_TONE = {
    Honesty.PROVEN: "good",
    Honesty.PRELIMINARY: "warn",
    Honesty.INCONCLUSIVE: "muted",
}


def _esc(s: object) -> str:
    return html.escape(str(s))


def _bar(baseline: float, hardened: float) -> str:
    b, h = round(baseline * 100), round(hardened * 100)
    return f"""
      <div class="ba">
        <div class="ba-row"><span class="ba-k">Baseline</span>
          <span class="track"><i class="fill bad" style="width:{b}%"></i></span>
          <span class="ba-v">{b}%</span></div>
        <div class="ba-row"><span class="ba-k">Hardened</span>
          <span class="track"><i class="fill good" style="width:{h}%"></i></span>
          <span class="ba-v">{h}%</span></div>
      </div>"""


def render_report_card_html(card: SafetyReportCard, idx: int = 0) -> str:
    gtone = _GRADE_TONE.get(card.grade, "muted")
    tags = "".join(
        f'<span class="chip">{_esc(t.llm)}</span><span class="chip">{_esc(t.asi)}</span>'
        for t in card.owasp_tags
        if t.llm
    )

    acc = ""
    if card.judge_accuracy:
        a = card.judge_accuracy
        acc = f"""
        <div class="block">
          <div class="block-h">Judge accuracy <span class="sub">vs {_esc(a.label_source)} · n={a.n}</span></div>
          <div class="metrics">
            <div class="m"><span class="mv">{a.precision.point*100:.0f}<i>%</i></span><span class="ml">precision</span><span class="ci">CI {a.precision.low*100:.0f}–{a.precision.high*100:.0f}</span></div>
            <div class="m"><span class="mv">{a.recall.point*100:.0f}<i>%</i></span><span class="ml">recall</span><span class="ci">CI {a.recall.low*100:.0f}–{a.recall.high*100:.0f}</span></div>
            <div class="m"><span class="mv">{a.f1:.2f}</span><span class="ml">F1</span></div>
            <div class="m"><span class="mv">{a.cohen_kappa:.2f}</span><span class="ml">κ vs oracle</span></div>
          </div>
        </div>"""
    elif card.judge_accuracy_note:
        acc = f"""
        <div class="block">
          <div class="block-h">Judge accuracy</div>
          <p class="sub">{_esc(card.judge_accuracy_note)}</p>
        </div>"""

    ba = ""
    if card.before_after:
        d = card.before_after
        htone = _HONESTY_TONE.get(d.honesty, "muted")
        ba = f"""
        <div class="block">
          <div class="block-h">Safety improvement <span class="pill {htone}">{d.honesty.value}</span></div>
          {_bar(d.baseline_issue_rate, d.hardened_issue_rate)}
          <div class="reduction">&minus;{d.absolute_reduction.point*100:.0f}% issue rate
            <span class="ci">CI {d.absolute_reduction.low*100:.0f}–{d.absolute_reduction.high*100:.0f} · McNemar p={d.mcnemar_p:.3f} · {d.n_pairs} paired</span></div>
        </div>"""

    fix = ""
    if card.fix_snippet:
        fid = f"fix{idx}"
        cmd = f"fusion harden --prompt your_prompt.txt --check {card.check}"
        fix = f"""
        <div class="block fix">
          <div class="block-h">Apply this fix <span class="sub">{_esc(card.fix_title)}</span>
            <button class="copy" type="button" onclick="fusionCopy('{fid}', this)">Copy</button></div>
          <pre id="{fid}" class="code">{_esc(card.fix_snippet)}</pre>
          <div class="auto">Auto-apply to your prompt: <code>{_esc(cmd)}</code></div>
        </div>"""

    demo = '<div class="demo">Demonstration — offline stand-in judge, not a real efficacy claim</div>' if card.demonstration else ""

    return f"""
      <section class="card">
        {demo}
        <header class="card-h">
          <span class="grade {gtone}">{_esc(card.grade)}</span>
          <div class="titles"><h2>{_esc(card.check.replace('_', ' '))}</h2><div class="tags">{tags}</div></div>
        </header>
        {acc}{ba}{fix}
        <footer class="prov">judge {_esc(card.judge_model)} · gold {_esc(card.gold_version)} · crosswalk {_esc(card.crosswalk_version)} · verify {_esc(card.verification_hash)}</footer>
      </section>"""


def render_overview_html(cards: list[SafetyReportCard]) -> str:
    codes = sorted({t.asi for c in cards for t in c.owasp_tags if t.asi})
    proven = sum(1 for c in cards if c.before_after and c.before_after.honesty == Honesty.PROVEN)
    prelim = sum(1 for c in cards if c.before_after and c.before_after.honesty == Honesty.PRELIMINARY)
    demo = any(c.demonstration for c in cards)
    banner = (
        '<p class="ov-note">These are demonstration numbers from an offline stand-in judge — they '
        "validate the methodology, not a live deployment. Adding a judge key and re-recording yields "
        "real numbers with no other change.</p>"
        if demo
        else ""
    )
    chips = "".join(f'<span class="chip">{_esc(x)}</span>' for x in codes)
    return f"""
      <div class="overview">
        <div class="ov-stats">
          <div class="ov"><span class="ov-v">{len(cards)}</span><span class="ov-l">safety checks</span></div>
          <div class="ov"><span class="ov-v">{proven}</span><span class="ov-l">proven</span></div>
          <div class="ov"><span class="ov-v">{prelim}</span><span class="ov-l">preliminary</span></div>
          <div class="ov ov-cov"><span class="ov-l">OWASP Agentic coverage</span><div class="tags">{chips}</div></div>
        </div>
        {banner}
      </div>"""


_CSS = """
:root{
  --bg:#f6f6f7; --card:#ffffff; --ink:#1a1a1f; --muted:#6b7280; --line:#e6e6ea;
  --soft:#f3f3f5; --accent:#504d9a; --wordmark:#66c4e1; --code-bg:#f4f4f6;
  --good:#15803d; --good-bg:#dcfce7; --warn:#b45309; --warn-bg:#fef3c7; --bad:#b91c1c; --bad-bg:#fee2e2;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0e0f13; --card:#16171d; --ink:#e8e8ec; --muted:#9aa0ac; --line:#262832;
  --soft:#1b1d25; --accent:#9a97e0; --wordmark:#66c4e1; --code-bg:#1b1d25;
  --good:#4ade80; --good-bg:#0f2a1a; --warn:#fbbf24; --warn-bg:#2a2110; --bad:#f87171; --bad-bg:#2c1414;
}}
:root[data-theme="dark"]{
  --bg:#0e0f13; --card:#16171d; --ink:#e8e8ec; --muted:#9aa0ac; --line:#262832;
  --soft:#1b1d25; --accent:#9a97e0; --wordmark:#66c4e1; --code-bg:#1b1d25;
  --good:#4ade80; --good-bg:#0f2a1a; --warn:#fbbf24; --warn-bg:#2a2110; --bad:#f87171; --bad-bg:#2c1414;
}
:root[data-theme="light"]{
  --bg:#f6f6f7; --card:#ffffff; --ink:#1a1a1f; --muted:#6b7280; --line:#e6e6ea;
  --soft:#f3f3f5; --accent:#504d9a; --wordmark:#66c4e1; --code-bg:#f4f4f6;
  --good:#15803d; --good-bg:#dcfce7; --warn:#b45309; --warn-bg:#fef3c7; --bad:#b91c1c; --bad-bg:#fee2e2;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.5;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:40px 20px 64px}
.masthead{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:24px}
.brand{font-size:22px;font-weight:700;letter-spacing:-.02em}
.brand span{color:var(--wordmark)}
.lede{color:var(--muted);margin-top:4px;font-size:15px;max-width:60ch}
.overview{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:24px}
.ov-stats{display:flex;flex-wrap:wrap;gap:28px;align-items:center}
.ov{display:flex;flex-direction:column}
.ov-v{font-size:26px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
.ov-l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.ov-cov{margin-left:auto}
.ov-note{color:var(--muted);font-size:13px;margin:14px 0 0;padding-top:14px;border-top:1px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;display:flex;flex-direction:column}
.demo{font-size:11.5px;color:var(--warn);background:var(--warn-bg);border:1px solid transparent;
  border-radius:7px;padding:6px 10px;margin-bottom:14px;font-weight:500}
.card-h{display:flex;gap:13px;align-items:center;margin-bottom:4px}
.grade{width:40px;height:40px;border-radius:9px;display:flex;align-items:center;justify-content:center;
  font-size:20px;font-weight:700;flex:none;border:1px solid}
.grade.good{color:var(--good);background:var(--good-bg);border-color:var(--good)}
.grade.warn{color:var(--warn);background:var(--warn-bg);border-color:var(--warn)}
.grade.bad{color:var(--bad);background:var(--bad-bg);border-color:var(--bad)}
.grade.muted{color:var(--muted);background:var(--soft);border-color:var(--line)}
.titles h2{margin:0;font-size:16px;font-weight:650;text-transform:capitalize;letter-spacing:-.01em}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}
.chip{font-size:11px;font-weight:600;color:var(--accent);border:1px solid var(--line);
  background:var(--soft);border-radius:6px;padding:1px 7px;font-variant-numeric:tabular-nums}
.block{border-top:1px solid var(--line);margin-top:16px;padding-top:14px}
.block-h{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}
.sub{font-weight:400;text-transform:none;letter-spacing:0;color:var(--muted);font-size:12px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.m{display:flex;flex-direction:column;gap:2px}
.mv{font-size:21px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1}
.mv i{font-size:13px;font-weight:600;color:var(--muted);font-style:normal;margin-left:1px}
.ml{font-size:11px;color:var(--muted)}
.ci{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums}
.pill{font-size:10.5px;font-weight:700;border-radius:999px;padding:2px 9px;margin-left:auto;letter-spacing:.03em}
.pill.good{color:var(--good);background:var(--good-bg)}
.pill.warn{color:var(--warn);background:var(--warn-bg)}
.pill.muted{color:var(--muted);background:var(--soft)}
.ba{display:flex;flex-direction:column;gap:8px}
.ba-row{display:flex;align-items:center;gap:10px}
.ba-k{width:64px;font-size:12px;color:var(--muted)}
.track{flex:1;height:8px;background:var(--soft);border-radius:999px;overflow:hidden}
.fill{display:block;height:100%;border-radius:999px}
.fill.bad{background:var(--bad)}
.fill.good{background:var(--good)}
.ba-v{width:36px;text-align:right;font-weight:700;font-size:13px;font-variant-numeric:tabular-nums}
.reduction{margin-top:11px;font-weight:700;font-size:15px;font-variant-numeric:tabular-nums}
.reduction .ci{display:block;font-weight:400;margin-top:2px}
.fix .block-h{align-items:center}
.copy{margin-left:auto;font:inherit;font-size:11px;font-weight:600;color:var(--accent);cursor:pointer;
  background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:3px 10px}
.copy:hover{border-color:var(--accent)}
.copy:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.code{margin:0;background:var(--code-bg);border:1px solid var(--line);border-radius:8px;padding:12px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px;line-height:1.55;
  color:var(--ink);white-space:pre-wrap;overflow-x:auto}
.auto{margin-top:9px;font-size:12px;color:var(--muted)}
.auto code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px;
  background:var(--code-bg);border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:var(--ink)}
.prov{margin-top:16px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10px;
  color:var(--muted);word-break:break-all}
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


def render_dashboard_html(cards: list[SafetyReportCard], title: str = "Safety Report") -> str:
    body = "".join(render_report_card_html(c, i) for i, c in enumerate(cards))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fusion First — {_esc(title)}</title><style>{_CSS}</style></head>
<body>
  <div class="wrap">
    <header class="masthead">
      <div class="brand">Fusion <span>First</span></div>
      <p class="lede">Agentic AI safety, proven. Every number carries a confidence interval or an honesty badge — and every check ships a fix you can apply in one command.</p>
    </header>
    {render_overview_html(cards)}
    <div class="grid">{body}</div>
  </div>
  <script>{_JS}</script>
</body></html>"""
