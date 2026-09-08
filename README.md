# AI Week — 매주 하나, 매일 기록.

AI 에이전트가 매주 종목을 하나 고르고, 그 판단이 맞았는지 매일 기록하는 공개 실험.
→ https://aiweek.kr

**이 리포가 public인 이유**: 진입가와 목표가가 사후에 바뀌지 않았다는 것을 커밋 이력으로 증명하기 위해서입니다. 성적표를 손대지 않았음을 보이는 유일한 방법입니다.

---

## 구조

```
data/picks.json      ← 사람이 쓴다. 게재 후 절대 수정 금지
data/record.json     ← 기계만 쓴다. 매 평일 16:00 KST 자동 갱신
scripts/update_prices.py   시세 수집 + 익절/손절 판정
scripts/build.py           정적 페이지 생성 → site/
.github/workflows/daily.yml  크론 → 갱신 → 빌드 → Pages 배포
```

이 분리가 실험의 신뢰 근거입니다. 사람이 쓰는 파일과 기계가 쓰는 파일을 섞지 마십시오.

## 발행 일정

**금요일 종가 기준으로 분석 → 다음 월요일 오전 8시 공개.**
성적은 공개일부터 평일 장 마감 후(16:00 KST) 매일 자동 갱신됩니다.

## 매주 하는 일

`data/picks.json` 의 `picks` 배열 맨 앞에 항목 하나를 추가하고 push. 끝.

```json
{
  "no": 2,
  "date": "2026-09-14",
  "basis_date": "2026-09-11",
  "name": "종목명",
  "code": "000000",
  "ticker": "000000.KS",
  "entry": 00000,
  "targets": { "t1": 0, "t2": 0, "stop": 0 },
  "buy_rule": "기준가 00,000원보다 낮을 때 분할 매수.",
  "valuation": {
    "analyst_avg": 0, "analyst_count": 4,
    "ai_fair": 0, "ai_method": "EPS 0원 × 목표 PER 00배", "eps": 0
  },
  "lede": "…", "buy": "…", "risk": "…",
  "sources": [{ "label": "…", "url": "…" }]
}
```

- `basis_date` 는 **직전 금요일**, `date` 는 **공개일(월요일)**.
- `entry` 는 **기준일(금요일) 종가**. 한 번 쓰면 고치지 않습니다.
- `buy_rule` 은 매수 조건(예: "기준가보다 낮을 때 분할 매수").
- `ticker` 는 야후 파이낸스 표기(`종목코드.KS`).
- 벤치마크(코스피) 기준값도 `basis_date` 종가로 잡히므로, 크론이 하루 걸러도 비교가 흔들리지 않습니다.

## 로컬에서 확인

```bash
python scripts/build.py && open site/index.html
```

## 최초 세팅 체크리스트

1. GitHub 리포를 **public** 으로 생성하고 push
2. Settings → Pages → Source 를 **GitHub Actions** 로 설정
3. Settings → Pages → Custom domain 에 `aiweek.kr` 입력 후 Save
4. DNS 전파 후 **Enforce HTTPS** 체크
5. Actions 탭 → `일일 성적 갱신 및 배포` → **Run workflow** 로 수동 1회 실행하여 시세 수집이 되는지 확인

## 시세 소스 교체

`scripts/update_prices.py` 의 `fetch_closes()` 함수 하나만 바꾸면 됩니다.
yfinance 가 막히면 한국투자증권 KIS Developers 오픈API(무료, 앱키 발급 필요)로 교체하십시오.

## 판정 규칙 (사이트 공개 규칙과 반드시 일치시킬 것)

종가 기준으로만 판정합니다. 장중 고가·저가는 쓰지 않습니다.

| 조건 | 상태 | 추적 |
| --- | --- | --- |
| 종가 ≤ 손절가 | 손절 | 종료 |
| 종가 ≥ 2차 익절가 | 2차 익절 | 종료 |
| 종가 ≥ 1차 익절가 | 1차 익절 | 계속 |
| 그 외 | 보유 중 | 계속 |

확정된 회차는 이후 어떤 경우에도 다시 계산하지 않습니다.
