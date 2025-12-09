# Gold Price History Data

금시세 위젯 앱을 위한 금시세 히스토리 데이터 저장소입니다.

## API Endpoint

```
https://taniar88.github.io/gold-data/history.json
```

## Data Format

```json
{
  "lastUpdated": "2024-12-09",
  "data": [
    {
      "date": "2024-12-09",
      "koreanPrice": 200.7,
      "internationalPrice": 2650.5,
      "internationalPriceKrw": 195.2,
      "exchangeRate": 1400.5,
      "premium": 2.82
    }
  ]
}
```

## Fields

| Field | Description | Unit |
|-------|-------------|------|
| date | 날짜 | YYYY-MM-DD |
| koreanPrice | 한국 금시세 | KRW/g |
| internationalPrice | 국제 금시세 | USD/oz |
| internationalPriceKrw | 국제 금시세 (원화 환산) | KRW/g |
| exchangeRate | 환율 | KRW/USD |
| premium | 김치 프리미엄 | % |

## Data Sources

- 국제 금시세: [Gold-API.com](https://www.gold-api.com/)
- 환율: [Frankfurter API](https://www.frankfurter.app/)
- 한국 금시세: [공공데이터포털](https://www.data.go.kr/)

## Update Schedule

- 매일 한국시간 오전 9시 자동 업데이트 (GitHub Actions)
- 90일간의 데이터 보관
