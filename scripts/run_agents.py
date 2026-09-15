#!/usr/bin/env python3
"""
2단계 파이프라인 실행기 — 월요일 06:00 KST에 GitHub Actions가 돌린다.

    run/<basis_date>/pool.json  (fetch_pool.py 가 먼저 만든다)
      → 1층 네 관찰 에이전트 (병렬·격리, 각자 웹 검색)
      → 2층 종합  → 3층 구성
      → picks.json 에 회차 항목 추가 (date = 다음 월요일)

각 에이전트의 시스템 프롬프트는 agents/*.md 파일 그대로다. 여기서 요약하거나 합치지 않는다.
1층 에이전트는 서로의 출력을 받지 않는다 — 입력은 자기 프롬프트 + README + pool.json 뿐.

필요한 비밀: ANTHROPIC_API_KEY
※ 2026-09-15 작성. 키가 없어 실제 실행은 아직 검증되지 않았다. 첫 실행은 workflow_dispatch 로 수동 확인할 것.
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
OBSERVERS = ["가치", "수급", "실적", "위험"]
FILES = {"가치": "01_가치.md", "수급": "02_수급.md", "실적": "03_실적.md", "위험": "04_위험.md",
         "종합": "05_종합.md", "구성": "06_구성.md"}
SEARCH_BUDGET = 40


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_json(text):
    """응답에서 JSON 하나를 꺼낸다. 코드펜스가 있으면 그 안, 없으면 첫 '{'부터."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(raw)


def call(system, user, *, web=False, max_tokens=16000):
    import anthropic

    client = anthropic.Anthropic()
    kwargs = dict(model=MODEL, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}])
    if web:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search",
                            "max_uses": SEARCH_BUDGET}]
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def run_observer(name, pool_text, basis, news_cutoff, outdir):
    system = read(os.path.join(AGENTS, FILES[name])) + "\n\n---\n\n" + read(os.path.join(AGENTS, "README.md"))
    user = (
        f"당신은 독립 실행되는 관찰 에이전트 '{name}'입니다. 다른 에이전트의 결과는 존재하지 않습니다.\n"
        f"기준일(가격) {basis}. 뉴스는 {news_cutoff} KST까지 허용.\n"
        f"후보군 pool.json:\n```json\n{pool_text}\n```\n"
        f"후보 전체에 대해 웹 검색으로 직접 조사하고, README의 공통 JSON 하나만 출력하십시오. "
        f"검색은 총 {SEARCH_BUDGET}회 이내. 산문 보고서 금지."
    )
    out = extract_json(call(system, user, web=True))
    with open(os.path.join(outdir, f"obs_{name}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    st = [o.get("stance") for o in out.get("opinions", [])]
    print(f"  1층 {name}: 편입 {st.count('편입')} / 보류 {st.count('보류')} / 반대 {st.count('반대')}")
    return out


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 else None
    if not basis:
        # 월요일 06:00 실행 기준 → 직전 금요일
        today = datetime.now(KST).date()
        basis = (today - timedelta(days=(today.weekday() - 4) % 7)).isoformat()
    outdir = os.path.join(ROOT, "run", basis)
    pool_path = os.path.join(outdir, "pool.json")
    if not os.path.exists(pool_path):
        sys.exit(f"pool.json 없음: {pool_path} — fetch_pool.py 를 먼저 실행")
    pool_text = read(pool_path)
    news_cutoff = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"기준일 {basis} · 뉴스 컷오프 {news_cutoff}")

    # 1층 — 병렬, 격리
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda n: run_observer(n, pool_text, basis, news_cutoff, outdir), OBSERVERS))

    # 2층
    inputs = {n: read(os.path.join(outdir, f"obs_{n}.json")) for n in OBSERVERS}
    user = "pool.json:\n```json\n" + pool_text + "\n```\n" + "".join(
        f"\nobs_{n}.json:\n```json\n{t}\n```\n" for n, t in inputs.items()
    ) + "\n프롬프트의 출력 JSON 하나만."
    synthesis = extract_json(call(read(os.path.join(AGENTS, FILES["종합"])), user))
    with open(os.path.join(outdir, "synthesis.json"), "w", encoding="utf-8") as f:
        json.dump(synthesis, f, ensure_ascii=False, indent=2)
    print("  2층 종합 완료 · 사실충돌",
          sum(len(c.get("fact_conflicts") or []) for c in synthesis.get("candidates", [])), "건")

    # 3층
    picks_path = os.path.join(ROOT, "data", "picks.json")
    picks = json.load(open(picks_path, encoding="utf-8"))
    next_no = max(p["no"] for p in picks["picks"]) + 1
    b = datetime.fromisoformat(basis).date()
    publish = (b + timedelta(days=(7 - b.weekday()) % 7 or 7)).isoformat()  # 다음 월요일
    user = (
        f"synthesis.json:\n```json\n{json.dumps(synthesis, ensure_ascii=False)}\n```\n"
        f"pool.json:\n```json\n{pool_text}\n```\n"
        f"회차 no={next_no}, phase=2, date=\"{publish}\", basis_date=\"{basis}\". "
        f"picks.json 회차 항목 JSON 하나만."
    )
    basket = extract_json(call(read(os.path.join(AGENTS, FILES["구성"])), user))
    with open(os.path.join(outdir, "basket.json"), "w", encoding="utf-8") as f:
        json.dump(basket, f, ensure_ascii=False, indent=2)
    names = [h["name"] for h in basket.get("holdings", [])]
    print(f"  3층 구성 완료 · {len(names)}종목: {', '.join(names)}")

    # picks.json 추가 — 사람이 쓰는 preface/lede/buy 는 초안 접두를 유지한다
    basket.update(no=next_no, phase=2, date=publish, basis_date=basis)
    picks["picks"].insert(0, basket)
    with open(picks_path, "w", encoding="utf-8") as f:
        json.dump(picks, f, ensure_ascii=False, indent=2)
    print(f"picks.json 에 제{next_no}회 추가 (공개 {publish})")


if __name__ == "__main__":
    main()
