#!/usr/bin/env python3
"""picks.json + record.json -> site/index.html (자체 완결 정적 페이지)"""

import json
import os
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site")
KST = timezone(timedelta(hours=9))


def won(n):
    return f"{round(n):,}"


def pct(v, sign=True):
    return f"{v:+.1f}%" if sign else f"{v:.1f}%"


def tone(v):
    """한국 증시 관행: 상승 빨강, 하락 파랑"""
    return "up" if v > 0 else ("down" if v < 0 else "flat")


STATUS_CLASS = {"손절": "bad", "1차 익절": "good", "2차 익절": "good", "보유 중": "hold"}

CSS = """
:root{
  --bg:#fbfaf8; --panel:#fff; --ink:#1a1a1a; --muted:#6b6660; --line:#e2ddd6;
  --accent:#8a1f1f; --up:#c0392b; --down:#1f5fa8; --good:#1f7a4d; --bad:#a33; --hold:#6b6660;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#16151a; --panel:#1e1d23; --ink:#eceaf0; --muted:#9a95a3; --line:#332f3a;
    --accent:#e0a3a3; --up:#ef6b5a; --down:#6ba3e8; --good:#5fc48d; --bad:#ef6b5a; --hold:#9a95a3;
  }
}
:root[data-theme="dark"]{
  --bg:#16151a; --panel:#1e1d23; --ink:#eceaf0; --muted:#9a95a3; --line:#332f3a;
  --accent:#e0a3a3; --up:#ef6b5a; --down:#6ba3e8; --good:#5fc48d; --bad:#ef6b5a; --hold:#9a95a3;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Noto Sans KR",-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased}
.wrap{max-width:680px;margin:0 auto;padding:0 20px}
h1,h2,h3{font-family:"Noto Serif KR",Georgia,serif;line-height:1.35;letter-spacing:-.01em}
a{color:inherit}

header.hero{border-bottom:2px solid var(--ink);margin-bottom:38px}
.hero-in{padding:44px 0 20px}
.brand{font-family:"Noto Serif KR",Georgia,serif;font-size:40px;font-weight:700;margin:0;letter-spacing:-.02em}
.tagline{color:var(--accent);font-weight:700;font-size:15px;margin:6px 0 0;letter-spacing:.02em}
.stamp{color:var(--muted);font-size:12.5px;margin-top:14px;font-variant-numeric:tabular-nums}

section{margin:0 0 46px}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.16em;color:var(--muted);
  text-transform:uppercase;margin:0 0 10px}
h2.sec{font-size:25px;margin:0 0 18px;padding-bottom:10px;border-bottom:1px solid var(--line)}

.intro p{margin:0 0 14px}
.intro strong{background:linear-gradient(transparent 62%,color-mix(in srgb,var(--accent) 22%,transparent) 62%)}

.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:24px;margin-bottom:20px}
.pick-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;margin-bottom:4px}
.pick-no{font-size:12px;font-weight:700;color:#fff;background:var(--accent);
  padding:3px 9px;border-radius:20px;letter-spacing:.04em}
.pick-name{font-family:"Noto Serif KR",Georgia,serif;font-size:29px;font-weight:700}
.pick-code{color:var(--muted);font-size:14px;font-variant-numeric:tabular-nums}
.pick-date{color:var(--muted);font-size:12.5px;margin-bottom:18px;font-variant-numeric:tabular-nums}
.lede{font-size:17.5px;line-height:1.72;margin:0 0 22px}

.tbl-scroll{overflow-x:auto;margin:0 0 22px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14.5px;font-variant-numeric:tabular-nums}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{font-size:11.5px;letter-spacing:.08em;color:var(--muted);font-weight:700;
  border-bottom:1.5px solid var(--ink);text-transform:uppercase}
tr.hl td{background:color-mix(in srgb,var(--accent) 7%,transparent);font-weight:700}
tr.now td{color:var(--muted)}

.block{margin:0 0 18px}
.block h3{font-size:15px;margin:0 0 6px;color:var(--accent);letter-spacing:.01em}
.block p{margin:0}

.targets{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:22px}
.t{border:1px solid var(--line);border-radius:8px;padding:12px;text-align:center;background:var(--bg)}
.t .lb{font-size:11.5px;color:var(--muted);letter-spacing:.05em}
.t .v{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:3px}
.t .d{font-size:12px;font-variant-numeric:tabular-nums}
.t.stop .v{color:var(--down)} .t.stop .d{color:var(--down)}
.t.t1 .v,.t.t2 .v{color:var(--up)} .t.t1 .d,.t.t2 .d{color:var(--up)}

.up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--muted)}
.badge{display:inline-block;font-size:11.5px;font-weight:700;padding:2px 8px;border-radius:4px;
  border:1px solid currentColor}
.badge.good{color:var(--good)} .badge.bad{color:var(--bad)} .badge.hold{color:var(--hold)}

.empty{color:var(--muted);font-size:14.5px;padding:18px;border:1px dashed var(--line);
  border-radius:8px;text-align:center}
.notice{font-size:13.5px;line-height:1.65;color:var(--muted);background:var(--bg);
  border-left:3px solid var(--accent);border-radius:0 6px 6px 0;padding:11px 14px;margin:0 0 18px}
.schedule{font-size:13.5px;color:var(--muted);margin:14px 0 0;padding-top:12px;
  border-top:1px solid var(--line)}
.schedule strong{color:var(--accent)}

ol.rules{padding-left:20px;margin:0}
ol.rules li{margin-bottom:9px}
ol.rules strong{font-weight:700}

.sources{font-size:13px;color:var(--muted);margin-top:20px;padding-top:14px;border-top:1px solid var(--line)}
.sources a{color:var(--muted)}

footer{border-top:1px solid var(--line);margin-top:20px;padding:26px 0 60px;
  font-size:12.5px;color:var(--muted);line-height:1.7}

@media(max-width:520px){
  .brand{font-size:32px} .pick-name{font-size:24px} h2.sec{font-size:21px}
  .lede{font-size:16.5px} .targets{grid-template-columns:1fr}
  .card{padding:18px}
}
"""

INTRO = """
<p>저는 아시아투데이에 「이영환의 에이전틱 이코노미」라는 칼럼을 쓰고 있습니다. 스무 회가 넘도록 AI가 무엇을 어떻게 바꾸고 있는지 설명해왔습니다. 그런데도 여전히 많은 분들이 이렇게 물으십니다. "그래서 그게 제 생활하고 무슨 상관입니까?"</p>
<p>그 질문에 말로 답하는 대신, 실험을 하나 해보기로 했습니다.</p>
<p>매주 AI 에이전트에게 종목을 하나 고르게 합니다. 무엇을 보고 왜 그렇게 판단했는지 숨기지 않고 그대로 공개합니다. 그리고 그 판단이 맞았는지 틀렸는지를 <strong>매일 기록합니다.</strong></p>
<p>저는 이 실험의 결과를 모릅니다. AI가 고른 종목이 열에 아홉 맞을 수도 있고, 반대로 처참하게 틀릴 수도 있습니다. 어느 쪽이든 그 기록을 지우지 않겠습니다.</p>
<p>함께 지켜봐 주시기 바랍니다.</p>
"""

RULES = [
    ("매주 한 종목, 월요일 오전 8시.", "직전 금요일 종가를 기준가로 삼고, 월요일 아침에 공개합니다."),
    ("매수 조건과 목표를 미리 공개합니다.", "매수 시점, 1차·2차 익절가, 손절가를 공개 시점에 모두 밝히고 이후에는 바꾸지 않습니다."),
    ("판정은 종가 기준입니다.", "손절가를 종가로 밑돌면 그 자리에서 손실을 확정해 기록합니다. 장중에 잠깐 스친 가격은 세지 않습니다."),
    ("성적은 매일 갱신됩니다.", "기준가 대비 수익률을 코스피 같은 기간 수익률과 나란히 놓습니다."),
    ("모든 회차는 영구 보존합니다.", "삭제도 수정도 하지 않습니다."),
]

DISCLAIMER = (
    "본 페이지는 투자 권유가 아니며, 어떤 종목의 매매도 권하지 않습니다. "
    "AI 에이전트의 판단 과정을 공개하고 그 결과를 관찰하는 것이 목적입니다. "
    "필자는 여기에 소개되는 기업들과 어떤 개인적 관계도 없으며, 투자 판단과 그 결과는 온전히 읽는 분의 몫입니다. "
    "혹시라도 관계가 생기면 그 즉시 공지하겠습니다. "
    "이 페이지는 전면 무료이며, 유료 구독이나 개별 종목 상담은 일절 제공하지 않습니다."
)


def render_pick(p, rec):
    v = p["valuation"]
    entry, t = p["entry"], p["targets"]
    now = rec.get("price")

    rows = [
        ("증권사 목표주가 평균 (%d곳)" % v["analyst_count"], v["analyst_avg"], ""),
        ("AI 산출 적정주가", v["ai_fair"], "hl"),
    ]
    html = [
        '<div class="card">',
        '<div class="pick-head">',
        f'<span class="pick-no">제{p["no"]}회</span>',
        f'<span class="pick-name">{p["name"]}</span>',
        f'<span class="pick-code">{p["code"]}</span>',
        "</div>",
        f'<div class="pick-date">기준일 {p.get("basis_date", p["date"])} 종가 {won(entry)}원'
        f' · 공개 {p["date"]}</div>',
        (f'<div class="notice">{p["note"]}</div>' if p.get("note") else ""),
        f'<p class="lede">{p["lede"]}</p>',
        '<div class="tbl-scroll"><table><thead><tr>',
        "<th>구분</th><th>가격</th><th>진입가 대비</th><th>적용 PER</th>",
        "</tr></thead><tbody>",
    ]
    for label, price, cls in rows:
        d = (price / entry - 1) * 100
        html.append(
            f'<tr class="{cls}"><td>{label}</td><td>{won(price)}원</td>'
            f'<td class="{tone(d)}">{pct(d)}</td><td>{price/v["eps"]:.1f}배</td></tr>'
        )
    if now:
        d = rec["return_pct"]
        html.append(
            f'<tr class="now"><td>현재가 ({rec["price_date"]})</td><td>{won(now)}원</td>'
            f'<td class="{tone(d)}">{pct(d)}</td><td>{now/v["eps"]:.1f}배</td></tr>'
        )
    else:
        html.append(
            f'<tr class="now"><td>진입가 ({p["date"]})</td><td>{won(entry)}원</td>'
            f'<td class="flat">—</td><td>{entry/v["eps"]:.1f}배</td></tr>'
        )
    html.append("</tbody></table></div>")
    html.append(
        f'<p style="font-size:13px;color:var(--muted);margin:-10px 0 20px">'
        f'적정주가 산식 — {v["ai_method"]}</p>'
    )

    html.append(f'<div class="block"><h3>매수 이유</h3><p>{p["buy"]}</p></div>')
    html.append(f'<div class="block"><h3>위험 요소</h3><p>{p["risk"]}</p></div>')
    if p.get("buy_rule"):
        html.append(
            f'<div class="block"><h3>매수 시점</h3><p>{p["buy_rule"]}</p></div>'
        )

    html.append('<div class="targets">')
    for cls, lb, val in [
        ("t1", "1차 익절", t["t1"]),
        ("t2", "2차 익절", t["t2"]),
        ("stop", "손절", t["stop"]),
    ]:
        d = (val / entry - 1) * 100
        html.append(
            f'<div class="t {cls}"><div class="lb">{lb}</div>'
            f'<div class="v">{won(val)}</div><div class="d">{pct(d)}</div></div>'
        )
    html.append("</div>")

    if p.get("sources"):
        links = " · ".join(
            f'<a href="{s["url"]}" target="_blank" rel="noopener">{s["label"]}</a>'
            for s in p["sources"]
        )
        html.append(f'<div class="sources">출처 — {links}</div>')
    html.append("</div>")
    return "".join(html)


def render_record(picks, entries):
    if not entries:
        return (
            '<div class="empty">첫 회차가 막 시작되었습니다. '
            "평일 장 마감 후 이 자리에 성적이 기록됩니다.</div>"
        )
    rows = []
    for p in picks:
        r = entries.get(str(p["no"]))
        if not r:
            continue
        cls = STATUS_CLASS.get(r["status"], "hold")
        rows.append(
            f'<tr><td>제{p["no"]}회</td><td>{p["name"]}</td>'
            f'<td>{won(p["entry"])}</td><td>{won(r["price"])}</td>'
            f'<td class="{tone(r["return_pct"])}">{pct(r["return_pct"])}</td>'
            f'<td class="{tone(r["alpha_pp"])}">{r["alpha_pp"]:+.1f}%p</td>'
            f'<td><span class="badge {cls}">{r["status"]}</span></td></tr>'
        )
    done = [e for e in entries.values() if e.get("closed")]
    wins = len([e for e in done if e["return_pct"] > 0])
    avg = sum(e["return_pct"] for e in entries.values()) / len(entries)
    summary = (
        f'<p style="font-size:14px;color:var(--muted);margin:0 0 14px">'
        f"누적 {len(entries)}회 · 확정 {len(done)}회"
        + (f" (승 {wins} / 패 {len(done)-wins})" if done else "")
        + f' · 평균 수익률 <span class="{tone(avg)}">{pct(avg)}</span></p>'
    )
    return (
        summary
        + '<div class="tbl-scroll"><table><thead><tr>'
        "<th>회차</th><th>종목</th><th>진입가</th><th>현재가</th>"
        "<th>수익률</th><th>코스피 대비</th><th>상태</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def main():
    picks_doc = json.load(open(os.path.join(ROOT, "data", "picks.json"), encoding="utf-8"))
    picks = sorted(picks_doc["picks"], key=lambda p: p["no"], reverse=True)
    site = picks_doc["site"]

    rec_path = os.path.join(ROOT, "data", "record.json")
    record = json.load(open(rec_path, encoding="utf-8")) if os.path.exists(rec_path) else {}
    entries = record.get("entries", {})

    latest = picks[0]
    past = picks[1:]

    rules_html = "".join(
        f"<li><strong>{a}</strong> {b}</li>" for a, b in RULES
    )
    past_html = (
        "".join(render_pick(p, entries.get(str(p["no"]), {})) for p in past)
        if past
        else '<div class="empty">아직 지난 회차가 없습니다.</div>'
    )
    stamp = record.get("updated_at") or datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    html = f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{site['title']} — {site['tagline']}</title>
<meta name="description" content="AI 에이전트가 매주 종목을 하나 고르고, 그 판단이 맞았는지 매일 기록합니다. 금요일 종가 기준, 월요일 오전 8시 공개.">
<meta property="og:title" content="{site['title']} — {site['tagline']}">
<meta property="og:description" content="AI 에이전트가 고른 종목의 성적을 매일 공개 기록하는 실험입니다.">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&family=Noto+Serif+KR:wght@600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body>

<header class="hero"><div class="wrap hero-in">
  <h1 class="brand">{site['title']}</h1>
  <p class="tagline">{site['tagline']}</p>
  <div class="stamp">마지막 갱신 {stamp} · 글 {site['author']}</div>
</div></header>

<div class="wrap">

<section class="intro">
  <p class="eyebrow">이 페이지에 대하여</p>
  {INTRO}
</section>

<section>
  <p class="eyebrow">This Week</p>
  <h2 class="sec">이번 주의 종목</h2>
  {render_pick(latest, entries.get(str(latest['no']), {}))}
</section>

<section>
  <p class="eyebrow">Track Record</p>
  <h2 class="sec">성적표</h2>
  {render_record(picks, entries)}
</section>

<section>
  <p class="eyebrow">Method</p>
  <h2 class="sec">실험의 규칙</h2>
  <p style="margin:0 0 14px">미리 정해 두고 시작합니다. 실험이 실험이려면 규칙이 결과보다 먼저 있어야 하니까요.</p>
  <ol class="rules">{rules_html}</ol>
  <p class="schedule">발행 일정 — 매주 <strong>금요일 종가</strong>를 기준으로 분석하고, 다음 <strong>월요일 오전 8시</strong>에 공개합니다. 성적은 그날부터 평일 장 마감 후 매일 갱신됩니다.</p>
</section>

<section>
  <p class="eyebrow">Archive</p>
  <h2 class="sec">지난 회차</h2>
  {past_html}
</section>

</div>

<footer><div class="wrap">
  <p>{DISCLAIMER}</p>
  <p>© {datetime.now(KST).year} {site['author']} · {site['domain']}</p>
</div></footer>

</body></html>
"""

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(OUT, "CNAME"), "w") as f:
        f.write(site["domain"] + "\n")
    print(f"빌드 완료 → site/index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
