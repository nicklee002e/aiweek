#!/usr/bin/env python3
"""
2단계 파이프라인 실행기 — 월요일 06:00 KST에 GitHub Actions가 돌린다.

    run/<basis_date>/pool.json  (fetch_pool.py 가 먼저 만든다)
      → 1층 일곱 관찰 에이전트 (병렬·격리, 각자 웹 검색)        obs_<관점>.json
      → 2층 종합                                              synthesis.json
      → 슈퍼에이전트: 충돌 분류·절차 선택·라운드 주선 (헌법)     super_plan.json, r<n>_<관점>.json, resolution.json
      → 3층 구성 (resolved_positions 기준, 합의도 불사용)        basket.json
      → picks.json 에 회차 항목 추가 (date = 다음 월요일)

각 에이전트의 시스템 프롬프트는 agents/*.md 파일 그대로다. 여기서 요약하거나 합치지 않는다.
1층 에이전트는 서로의 출력을 받지 않는다. 라운드에서는 슈퍼에이전트가 인용한 상대 입장만 본다.

슈퍼에이전트는 헌법.md 의 닫힌 메뉴에서만 절차를 고른다. 라운드는 충돌당 최대 3회(헌법 9절 8항).
상신(escalate)된 쟁점은 사람이 답하지 않으면 그 종목을 담지 않고 '미해소'로 표시한다(헌법 10절).

필요한 비밀: ANTHROPIC_API_KEY
※ 2026-10-08 개정. 키가 없어 실제 실행은 아직 검증되지 않았다. 첫 실행은 workflow_dispatch 로 수동 확인할 것.
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "agents")
KST = timezone(timedelta(hours=9))
MODEL = os.environ.get("AIWEEK_MODEL", "claude-sonnet-4-5")
OBSERVERS = ["가치", "수급", "실적", "위험", "매크로", "산업", "기술"]
FILES = {"가치": "01_가치.md", "수급": "02_수급.md", "실적": "03_실적.md", "위험": "04_위험.md",
         "매크로": "05_매크로.md", "산업": "06_산업.md", "기술": "07_기술.md",
         "종합": "08_종합.md", "구성": "09_구성.md",
         "슈퍼": "10_슈퍼에이전트.md", "라운드": "11_협상라운드.md", "헌법": "헌법.md"}
SEARCH_BUDGET = 40
MAX_ROUNDS = 3  # 헌법 9절 8항


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def save(outdir, name, obj):
    with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def extract_json(text):
    """응답에서 JSON 하나를 꺼낸다. 코드펜스가 있으면 그 안, 없으면 첫 '{'부터."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(raw)


def call(system, user, *, web=False, max_tokens=16000, max_uses=SEARCH_BUDGET):
    import anthropic

    client = anthropic.Anthropic()
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}])
    if web:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}]
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def fence(label, obj):
    return f"\n{label}:\n```json\n{json.dumps(obj, ensure_ascii=False)}\n```\n"


# ---------------------------------------------------------------- 1층
def observer_system(name):
    return read(os.path.join(AGENTS, FILES[name])) + "\n\n---\n\n" + read(os.path.join(AGENTS, "README.md"))


def run_observer(name, pool, basis, news_cutoff, outdir):
    user = (
        f"당신은 독립 실행되는 관찰 에이전트 '{name}'입니다. 다른 에이전트의 결과는 존재하지 않습니다.\n"
        f"기준일(가격) {basis}. 뉴스는 {news_cutoff} KST까지 허용. 기준일 이후 가격 금지.\n"
        + fence("후보군 pool.json", pool)
        + f"후보 전체에 대해 웹 검색으로 직접 조사하고, README의 공통 JSON 하나만 출력하십시오. "
        f"검색은 총 {SEARCH_BUDGET}회 이내. 산문 보고서 금지."
    )
    out = extract_json(call(observer_system(name), user, web=True))
    save(outdir, f"obs_{name}.json", out)
    st = [o.get("stance") for o in out.get("opinions", [])]
    print(f"  1층 {name}: 편입 {st.count('편입')} / 보류 {st.count('보류')} / 반대 {st.count('반대')}")
    return out


# ---------------------------------------------------------------- 슈퍼에이전트
def super_system():
    return (read(os.path.join(AGENTS, FILES["헌법"])) + "\n\n---\n\n"
            + read(os.path.join(AGENTS, FILES["슈퍼"])) + "\n\n---\n\n"
            + read(os.path.join(AGENTS, FILES["라운드"])))


def super_plan(synthesis, obs, basis, outdir):
    """1·2단계 — 충돌 분류, 절차 선택, F 즉시 검증, 1라운드 질문."""
    user = (
        f"기준일 {basis}. 1단계·2단계를 수행하고 라운드가 필요한 충돌마다 1라운드 질문을 만드십시오. "
        "찬성 0·반대 4 이상 종목은 충돌이 아닙니다. F 충돌은 지금 바로 검증으로 확정하십시오. "
        "묶음을 완성할 수 없으면 재계획(R) 질문도 만드십시오. 종목에 대한 의견은 금지.\n"
        + fence("synthesis.json", synthesis)
        + "".join(fence(f"obs_{n}.json", o) for n, o in obs.items())
        + "\n출력: {conflicts:[{id, subject, type, tension, procedure, why, resolved_now, round1_questions:[{to, question}]}], "
          "replans:[{trigger, question_to_all}], skipped:[{subject, reason}]} JSON 하나만."
    )
    plan = extract_json(call(super_system(), user, max_tokens=24000))
    save(outdir, "super_plan.json", plan)
    return plan


def questions_for(agent, plan, round_no, prior):
    """이 관점에게 갈 질문 묶음. 1라운드는 plan 에서, 2라운드 이후는 직전 판정(prior)의 round{n}_questions 에서."""
    qs = []
    if round_no == 1:
        for c in plan.get("conflicts", []):
            for q in c.get("round1_questions", []):
                to = q.get("to", "")
                if to.startswith(agent) and "알림" not in to:
                    qs.append({"conflict_id": c["id"], "subject": c.get("subject"),
                               "procedure": c.get("procedure"), "question": q["question"]})
        for r in plan.get("replans", []):
            qs.append({"conflict_id": "R", "subject": r.get("trigger"), "procedure": "replan",
                       "question": r.get("question_to_all")})
    else:
        for q in (prior or {}).get(f"round{round_no}_questions", []):
            to = q.get("to", "")
            if to == "all" or to.startswith(agent):
                qs.append(q)
    return qs


def run_round(agent, qs, round_no, obs_self, basis, outdir):
    """관점 하나가 라운드에 답한다. 자기 처음 소견 + 슈퍼에이전트의 질문(상대 원문 인용 포함)만 받는다."""
    system = observer_system(agent) + "\n\n---\n\n" + read(os.path.join(AGENTS, FILES["라운드"]))
    user = (
        f"협상 라운드 {round_no}. 당신은 {agent} 관점입니다. 처음 소견은 아래에 있고 바뀌지 않습니다. "
        f"기준일 {basis} 이후 가격·뉴스 금지. 웹 검색은 조건 확인에 꼭 필요할 때만 2회 이내.\n"
        + fence("당신의 처음 소견 obs", obs_self)
        + fence("질문", qs)
        + "\n질문마다 11_협상라운드.md 의 JSON 하나씩, 배열로 출력. 조건은 헌법 6절의 세 화폐 안에서만."
    )
    txt = call(system, user, web=True, max_uses=2)
    m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", txt, re.S)
    out = json.loads(m.group(1) if m else txt[txt.find("["):txt.rfind("]") + 1])
    save(outdir, f"r{round_no}_{agent}.json", out)
    return out


def super_adjudicate(plan, responses, round_no, prior, basis, outdir):
    """3·4단계 — 응답을 읽고 판정. 다음 라운드가 필요하면 round{n+1}_questions 를 낸다."""
    user = (
        f"기준일 {basis}. 라운드 {round_no} 응답입니다. 3단계(판정)와 4단계(기록)를 수행하십시오. "
        f"라운드 상한은 {MAX_ROUNDS}회이며 넘기면 상신입니다. 원문 소견은 고치지 않습니다. "
        "자기 해석으로 판정한 곳은 audit_flags 에 적으십시오. "
        f"다음 라운드가 필요하면 round{round_no + 1}_questions:[{{to, conflict_id, question}}] 를, "
        "끝났으면 빈 배열을 내십시오. 상신할 쟁점은 escalations:[{subject, summary, options:[a,b]}] 에.\n"
        + fence("super_plan.json", plan)
        + (fence("직전 판정", prior) if prior else "")
        + "".join(fence(f"r{round_no}_{a}.json", r) for a, r in responses.items())
        + "\n출력: 10_슈퍼에이전트.md 4단계 형식 JSON 하나만 (conflicts, replans, escalations, resolved_positions, "
          f"agreement_raw, round{round_no + 1}_questions, log_note)."
    )
    res = extract_json(call(super_system(), user, max_tokens=24000))
    save(outdir, f"resolution_r{round_no}.json", res)
    return res


def run_super(synthesis, obs, basis, outdir):
    plan = super_plan(synthesis, obs, basis, outdir)
    n_conf = len(plan.get("conflicts", []))
    print(f"  슈퍼: 충돌 {n_conf}건 분류 · 재계획 {len(plan.get('replans', []))}건")
    prior = None
    for rn in range(1, MAX_ROUNDS + 1):
        bundles = {a: questions_for(a, plan, rn, prior) for a in OBSERVERS}
        bundles = {a: q for a, q in bundles.items() if q}
        if not bundles:
            break
        print(f"  라운드 {rn}: {', '.join(f'{a}({len(q)})' for a, q in bundles.items())}")
        with ThreadPoolExecutor(max_workers=7) as ex:
            futs = {a: ex.submit(run_round, a, q, rn, obs[a], basis, outdir) for a, q in bundles.items()}
            responses = {a: f.result() for a, f in futs.items()}
        prior = super_adjudicate(plan, responses, rn, prior, basis, outdir)
        if not prior.get(f"round{rn + 1}_questions"):
            break
    if prior is None:  # 라운드가 필요 없었음 — F 만 있었거나 충돌 없음
        prior = {"conflicts": plan.get("conflicts", []), "replans": [], "escalations": [],
                 "resolved_positions": {}, "log_note": "라운드 없음"}
    # 헌법 10절 — 상신 타임아웃: 사람이 답할 통로가 이 실행기에 없으므로, 상신 쟁점은 '미해소'로 고정한다
    prior["unresolved"] = [
        {"code": e.get("code"), "name": e.get("subject"), "summary": e.get("summary"), "options": e.get("options", [])}
        for e in prior.get("escalations", [])
    ]
    save(outdir, "resolution.json", prior)
    print(f"  슈퍼: 확정 {len(prior.get('resolved_positions', {}))}건 · 미해소 {len(prior['unresolved'])}건")
    return prior


# ---------------------------------------------------------------- main
def last_trading_day(d):
    """직전 거래일 — 주말만 거른다. 공휴일(추석 등)은 basis 를 인자로 넘겨 처리한다."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    if not basis:
        today = datetime.now(KST).date()
        basis = last_trading_day(today - timedelta(days=(today.weekday() - 4) % 7)).isoformat()
    outdir = os.path.join(ROOT, "run", basis)
    pool_path = os.path.join(outdir, "pool.json")
    if not os.path.exists(pool_path):
        sys.exit(f"pool.json 없음: {pool_path} — fetch_pool.py 를 먼저 실행")
    pool = json.load(open(pool_path, encoding="utf-8"))
    news_cutoff = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"기준일 {basis} · 뉴스 컷오프 {news_cutoff}")

    # 1층 — 병렬, 격리
    with ThreadPoolExecutor(max_workers=7) as ex:
        obs = dict(zip(OBSERVERS, ex.map(lambda n: run_observer(n, pool, basis, news_cutoff, outdir), OBSERVERS)))

    # 2층
    user = fence("pool.json", pool) + "".join(fence(f"obs_{n}.json", o) for n, o in obs.items()) + "\n프롬프트의 출력 JSON 하나만."
    synthesis = extract_json(call(read(os.path.join(AGENTS, FILES["종합"])), user, max_tokens=24000))
    save(outdir, "synthesis.json", synthesis)
    print("  2층 종합 완료 · 사실충돌",
          sum(len(c.get("fact_conflicts") or []) for c in synthesis.get("candidates", [])), "건")

    # 슈퍼에이전트 — 절차 선택·라운드
    resolution = run_super(synthesis, obs, basis, outdir)

    # 3층
    picks_path = os.path.join(ROOT, "data", "picks.json")
    picks = json.load(open(picks_path, encoding="utf-8"))
    next_no = max(p["no"] for p in picks["picks"]) + 1
    b = datetime.fromisoformat(basis).date()
    publish = (b + timedelta(days=(7 - b.weekday()) % 7 or 7)).isoformat()  # 다음 월요일
    user = (
        fence("resolution.json", resolution) + fence("synthesis.json", synthesis) + fence("pool.json", pool)
        + f"회차 no={next_no}, phase=2, date=\"{publish}\", basis_date=\"{basis}\". "
          "resolved_positions 가 입력의 기준이다. 종목마다 procedure·outcome·terms(stop_note, checkpoints, contrarian)를 "
          "resolution 에서 옮겨 적는다. resolution.unresolved 는 그대로 unresolved 필드로, resolution 전체는 resolution 필드로 넣는다. "
          "picks.json 회차 항목 JSON 하나만."
    )
    basket = extract_json(call(read(os.path.join(AGENTS, FILES["구성"])), user, max_tokens=24000))
    basket.setdefault("resolution", resolution)
    basket.setdefault("unresolved", resolution.get("unresolved", []))
    save(outdir, "basket.json", basket)
    names = [h["name"] for h in basket.get("holdings", [])]
    print(f"  3층 구성 완료 · {len(names)}종목: {', '.join(names)}")

    basket.update(no=next_no, phase=2, date=publish, basis_date=basis)
    picks["picks"].insert(0, basket)
    with open(picks_path, "w", encoding="utf-8") as f:
        json.dump(picks, f, ensure_ascii=False, indent=2)
    print(f"picks.json 에 제{next_no}회 추가 (공개 {publish})")


if __name__ == "__main__":
    main()
