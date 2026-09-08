#!/usr/bin/env python3
"""
평일 장 마감 후 실행. 각 픽의 종가를 받아 record.json을 갱신한다.

원칙
  - picks.json 은 절대 건드리지 않는다 (사람이 쓰는 불변 데이터)
  - 판정은 종가 기준. 장중 고가/저가는 쓰지 않는다
  - 한 번 확정(손절 / 2차 익절)된 회차는 다시 계산하지 않는다
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "data", "picks.json")
RECORD = os.path.join(ROOT, "data", "record.json")
KST = timezone(timedelta(hours=9))
BENCHMARK = "^KS11"  # 코스피 지수


# ---------------------------------------------------------------- 시세 수집
# 교체 지점: yfinance 가 막히면 이 함수 하나만 바꾸면 된다.
# 대안 — 한국투자증권 KIS Developers 오픈API (앱키 필요, 공식)
def fetch_closes(tickers):
    """{ticker: (date_str, close)} 반환. 실패한 종목은 키를 넣지 않는다."""
    import yfinance as yf

    out = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="10d")
            if hist.empty:
                print(f"  [warn] {t}: 데이터 없음", file=sys.stderr)
                continue
            last = hist.iloc[-1]
            out[t] = (str(hist.index[-1].date()), float(last["Close"]))
        except Exception as e:
            print(f"  [warn] {t}: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- 판정
def judge(pick, price):
    """종가 기준 상태 판정. 확정 상태면 추적을 멈춘다."""
    t = pick["targets"]
    if price <= t["stop"]:
        return "손절", True
    if price >= t["t2"]:
        return "2차 익절", True
    if price >= t["t1"]:
        return "1차 익절", False
    return "보유 중", False


def main():
    picks = json.load(open(PICKS, encoding="utf-8"))["picks"]

    record = {"entries": {}}
    if os.path.exists(RECORD):
        try:
            record = json.load(open(RECORD, encoding="utf-8"))
        except json.JSONDecodeError:
            print("[warn] record.json 파손 — 새로 만든다", file=sys.stderr)
    entries = record.setdefault("entries", {})

    # 아직 확정되지 않은 회차만 조회한다
    open_picks = [p for p in picks if not entries.get(str(p["no"]), {}).get("closed")]
    if not open_picks:
        print("확정되지 않은 회차 없음 — 지수만 갱신")

    tickers = sorted({p["ticker"] for p in open_picks} | {BENCHMARK})
    print(f"조회: {', '.join(tickers)}")
    closes = fetch_closes(tickers)

    if BENCHMARK not in closes:
        print("[error] 벤치마크 조회 실패 — 이번 회차는 갱신하지 않는다", file=sys.stderr)
        return 1

    bench_date, bench_close = closes[BENCHMARK]
    record["benchmark"] = {"ticker": BENCHMARK, "date": bench_date, "close": bench_close}

    changed = 0
    for p in open_picks:
        key = str(p["no"])
        if p["ticker"] not in closes:
            continue
        date_str, price = closes[p["ticker"]]
        status, closed = judge(p, price)
        entry = p["entry"]
        ret = (price / entry - 1) * 100

        prev = entries.get(key, {})
        # 벤치마크 기준값은 최초 1회만 기록하고 이후 고정한다
        bench_entry = prev.get("bench_entry")
        if bench_entry is None:
            bench_entry = bench_close
        bench_ret = (bench_close / bench_entry - 1) * 100

        entries[key] = {
            "no": p["no"],
            "price": round(price),
            "price_date": date_str,
            "return_pct": round(ret, 2),
            "status": status,
            "closed": closed,
            "bench_entry": bench_entry,
            "bench_return_pct": round(bench_ret, 2),
            "alpha_pp": round(ret - bench_ret, 2),
        }
        if closed and not prev.get("closed"):
            entries[key]["closed_on"] = date_str
            print(f"  ** 제{p['no']}회 {p['name']} → {status} 확정 ({ret:+.2f}%)")
        changed += 1
        print(f"  제{p['no']}회 {p['name']}: {price:,.0f}원 {ret:+.2f}% [{status}]")

    record["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    with open(RECORD, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"record.json 갱신 완료 ({changed}개 회차)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
