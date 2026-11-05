# Financial Forecast Lab

Texas Instruments(TXN)의 실제 재무자료로 분기 매출·영업이익을 예측하고, 한 해의 간이 FCFF로 연결하는 모의 재무예측 프로젝트입니다.

## 데이터와 실행

- 주 분석: **2012Q1~2025Q4, 56개 분기**, SEC 연결 재무자료, 단위 백만 달러
- 추가 비교: 2026Q1~Q3, 3개 분기를 별도 표시
- 최종 모의 예측 기준일: **2026-02-06**. 이 시점까지의 자료로 2026년 4개 분기를 예측합니다.
- 최초 확인되는 10-Q·10-K 수치를 사용하고 각 학습 시점 이후의 제출 자료는 제외합니다.
- 원자료·조회 시각·해시: `data/raw/`. 분기화와 공시 출처: `outputs/final_quarterly_financials.csv`, `final_lineage.json`.

```bash
python3 -m pip install -r requirements.txt
python3 run_final.py
python3 -m unittest discover -s tests -p test_release.py -v
```

저장된 원자료로 오프라인 실행합니다. 새 원자료가 필요할 때는 이름과 연락처를 담은 `SEC_USER_AGENT`를 지정하고 `python3 download_data.py`를 실행합니다.

## 최종 비교

검증은 2019~2023년 20분기, 비교 평가는 2024~2025년 8분기입니다. 개선 후보는 이전 평가 결과를 확인한 뒤 설계했으므로 **탐색적 개선 결과**로 표시합니다. 2026년 3분기까지의 추가 비교도 별도 기록하며 재튜닝에 사용하지 않습니다.

| 항목 | 기존 방식 MAE | 개선 후보 MAE |
|---|---:|---:|
| 매출: Holt–Winters → 회귀·Holt–Winters 반반 결합 | 162.99 | 145.33 |
| 영업이익: 동일 결합 매출 아래 수준 회귀 → 변화량 회귀 | 158.40 | 96.61 |
| 연간 간이 FCFF: 기존 연결 → 개선 후보 연결, 2개 연도 | 833.26 | 922.51 |

각 행의 비교 조건은 다릅니다. 매출의 순수 회귀 MAE는 128.71로 결합보다 작았습니다. 후보 선택은 검증 구간 MAE로 수행했습니다. 연간 FCFF MAE와 추가 2026년 지표는 일관되게 개선되지 않아 **기본 FCFF 연결은 기존 방식으로 유지**합니다.

| 2026년 모의 계산 | 기존 기본값 | 개선 후보 |
|---|---:|---:|
| 연간 매출 | 18,193.41 | 17,965.73 |
| 조건부 영업이익 | 7,015.21 | 5,614.14 |
| 간이 FCFF | 2,379.43 | 1,439.92 |

간이 FCFF는 가정 세율 25%, 과거 CAPEX·감가상각 비율과 매출채권+재고−매입채무를 사용합니다. 전체 영업운전자본·무형자산 상각·구체적 투자계획은 추가 검토 항목입니다.

## 공개 파일

- `forecast_lab/`: 공시 추출, 예측모형, 현금흐름 연결, 입력 검사
- `release_plan.json`: 후보와 평가 설계
- `run_final.py`: 전체 재현
- `outputs/final_metrics.csv`: 검증·평가·추가 비교 점수
- `outputs/final_annual_bridge_backtest.csv`: 연간 현금흐름 비교
- `outputs/final_forecast_2026.csv`, `final_fcff_2026.csv`, `final_results.json`: 최종 출력
- `tests/test_release.py`: 공개 코드 검증 20개

2012년 영업이익 +1, 2013년 매출 −1백만 달러의 연간 합계 차이는 `final_annual_reconciliation.csv`에 남겼습니다. 최근 평가 구간은 추출한 흐름 항목의 연간 합계와 일치합니다.

## 참고

[SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · [TI 2025 10-K](https://www.sec.gov/Archives/edgar/data/97476/000009747626000059/txn-20251231.htm) · [Forecasting: Principles and Practice](https://otexts.com/fpp3/toolbox.html)
