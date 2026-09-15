# 크립토 단타 전략 백테스트 (추세추종 / 유동성 스윕)

두 전략의 규칙을 코드로 정형화해 R-배수(위험 단위) 기준으로 시뮬레이션합니다.

## ⚠️ 이 환경에서 실행 시 알아야 할 것

이 백테스트를 만든 세션(샌드박스)은 **외부 네트워크가 정책상 차단**되어
있어 Binance/Bybit 등 거래소 API에서 실제 시세를 받아올 수 없었습니다
(`api.binance.com`, `fapi.binance.com`, `api.bybit.com` 전부 `403 policy
denial`). 그래서:

- 코드는 **합성(가짜) 랜덤워크 데이터로 파이프라인 동작만 검증**했습니다
  (`generate_sample_data.py`) — 에러 없이 끝까지 도는지 확인한 것이지,
  전략이 실제로 수익성이 있는지와는 무관합니다.
- **실전 검증은 본인 PC/서버에서 실제 데이터로 실행**해야 합니다.

## 실행 방법

```bash
pip install -r requirements.txt
```

### 1. 실제 데이터 준비

CSV 형식(`timestamp,open,high,low,close,volume`)의 1시간봉이 필요합니다.

- **ccxt** (거래소 API 통합 라이브러리, 로컬에서 실행):
  ```bash
  pip install ccxt
  python -c "
  import ccxt, pandas as pd
  ex = ccxt.binance()
  ohlcv = ex.fetch_ohlcv('BTC/USDT', '1h', limit=1000)  # 페이지네이션 필요 (최대 1000개/요청)
  df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
  df.to_csv('btcusdt_1h.csv', index=False)
  "
  ```
  100회 이상 표본을 보려면 최소 1~2년치 1H 데이터(약 8,760~17,520행)를
  여러 번 나눠 받아 이어붙여야 합니다.
- 또는 [Binance 공개 데이터 아카이브](https://data.binance.vision/)에서
  월별 kline zip을 받아 CSV로 변환.
- 또는 TradingView에서 Export 후 컬럼명을 위 스키마에 맞게 정리.

### 2. 백테스트 실행

```bash
python run.py --data btcusdt_1h.csv --strategy trend    # 추세추종만
python run.py --data btcusdt_1h.csv --strategy sweep    # 유동성 스윕만
python run.py --data btcusdt_1h.csv --strategy both      # 둘 다
```

### 3. 스모크 테스트 (합성 데이터, 코드 검증용)

```bash
python generate_sample_data.py --bars 9600 --out sample.csv
python run.py --data sample.csv --strategy both
```

## 반드시 확인해야 할 가정 (원본 룰과 다를 수 있음)

메시지에서 "지금 하는 EMA 되돌림 진입은 그대로 두고"라고 하셨는데, 그
기존 룰이 정확히 뭔지는 대화에 없어서 **제가 임의로 정형화**했습니다.
`strategies.py`의 `PullbackConfig`/`SweepConfig`로 조정 가능:

| 항목 | 이 구현의 정의 | 확인 필요 |
|---|---|---|
| 되돌림 진입 | 1H 저가가 EMA20에 닿은 뒤, 몸통 ≥ 0.5×ATR인 양봉이 EMA20 위로 마감 | 원래 쓰던 확인봉 조건과 다를 수 있음 |
| 되돌림 저점 | 진입 시점 이전 5봉 중 최저가 | lookback 길이 확인 |
| 아시아 세션 | 00:00~08:00 UTC | 거래소/기준에 따라 다름 (도쿄 09:00 KST 개장 기준이면 조정 필요) |
| 스윕 익절 | 반대편 가장 가까운 레벨(스윙/전일/아시아) | "직전 스윙 또는 전일 반대 고저" 중 어느 걸 우선할지는 가장 가까운 것으로 임의 결정 |
| 동시 히트 처리 | 같은 봉에서 손절·익절 모두 터치되면 **손절 우선** 처리 (보수적 가정) | 분봉 데이터 없이는 어느 게 먼저인지 알 수 없음 |

## 한계

- 수수료·슬리피지·펀딩비 미반영 (무기한 계약이면 펀딩비 영향 상당함 — 다음 개선 포인트로 추가 가능)
- 1H 봉 기준 단일 포지션만 시뮬레이션 (동시 진입/피라미딩 없음)
- 스윕 전략의 "50% 되돌림 지정가 진입" 변형은 미구현 (종가 진입만 구현됨)
