#!/usr/bin/env python3
"""
0층 — 후보군 + 거래소 종가 + DART 재무. agents/00_후보군.md 의 규칙을 코드로 옮긴 것.

데이터 출처 (2026-09-15 확정)
  종가   : KRX Open API  https://openapi.krx.co.kr   (KRX_API_KEY)
  재무   : DART OpenAPI  https://opendart.fss.or.kr  (DART_API_KEY) — 최근 4개 분기 합산 EPS/BPS
  후보군 : 기준일 마감 시황 기사 언급 종목 + 저PBR 업종 시총 상위 (이 부분은 아직 사람이 pool_seed.json 으로 준다)

※ 두 API 모두 키가 발급된 뒤에야 엔드포인트·필드명을 실제 응답으로 확인할 수 있다.
   아래 요청 형식은 각 기관의 공개 문서 기준 초안이며, 첫 실행에서 맞춰야 한다.
   키가 없으면 즉시 실패한다 — 조용히 언론 종가로 대체하지 않는다.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))


def need(var):
    v = os.environ.get(var)
    if not v:
        sys.exit(f"[fetch_pool] {var} 가 없습니다. 거래소·감독원 데이터 없이 후보군을 만들지 않습니다.")
    return v


def krx_close(code, basis, key):
    """KRX Open API 유가증권 일별시세. basis 는 YYYYMMDD."""
    r = requests.get(
        "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
        headers={"AUTH_KEY": key}, params={"basDd": basis}, timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("OutBlock_1", [])
    for row in rows:
        if row.get("ISU_CD", "").endswith(code) or row.get("ISU_CD") == code:
            return int(str(row["TDD_CLSPRC"]).replace(",", ""))
    return None


def dart_fundamentals(corp_code, key):
    """최근 4개 분기 순이익 합산 / 자본총계 → EPS, BPS. (단일회사 주요계정 API)
    corp_code 는 DART 고유번호(8자리). 종목코드→고유번호 매핑은 corpCode.xml 로 한 번 받아 둔다."""
    # 초안: 첫 실행에서 필드명 확인 필요
    return None


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    if not basis:
        today = datetime.now(KST).date()
        basis = (today - timedelta(days=(today.weekday() - 4) % 7)).isoformat()
    krx_key = need("KRX_API_KEY")
    need("DART_API_KEY")

    outdir = os.path.join(ROOT, "run", basis)
    os.makedirs(outdir, exist_ok=True)
    seed_path = os.path.join(outdir, "pool_seed.json")
    if not os.path.exists(seed_path):
        sys.exit(f"[fetch_pool] {seed_path} 없음 — 후보군 규칙(00_후보군.md)대로 종목 목록을 먼저 둘 것")
    seed = json.load(open(seed_path, encoding="utf-8"))

    picks = json.load(open(os.path.join(ROOT, "data", "picks.json"), encoding="utf-8"))["picks"]
    held = {h["code"] for p in picks for h in (p.get("holdings") or [{"code": p.get("code")}])}

    pool, excluded, gaps = [], [], []
    for s in seed["pool"]:
        if s["code"] in held:
            excluded.append({"code": s["code"], "name": s["name"], "reason": "진행 중 회차 보유"})
            continue
        close = krx_close(s["code"], basis.replace("-", ""), krx_key)
        if close is None:
            gaps.append(f"{s['name']} 종가 없음")
        s["close_krx"] = close
        s["fundamentals"] = dart_fundamentals(s.get("corp_code"), os.environ["DART_API_KEY"])
        pool.append(s)

    out = {"basis_date": basis, "rule_version": "2026-09-15", "pool": pool,
           "excluded": excluded, "data_gaps": gaps}
    with open(os.path.join(outdir, "pool.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"pool.json: {len(pool)}종목, 제외 {len(excluded)}, 결측 {len(gaps)}")


if __name__ == "__main__":
    main()
