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

## Project Structure

```
gold-data/
├── .github/
│   └── workflows/
│       ├── update-gold-price.yml   # 매일 자동 업데이트
│       └── init-history.yml        # 초기 히스토리 생성 (수동)
├── scripts/
│   ├── update_price.py             # 일일 금시세 업데이트
│   ├── init_history.py             # LBMA 데이터로 초기화
│   └── parse_woori_pdf.py          # 우리은행 PDF 파싱 (미완성)
├── 금시세/                          # 우리은행 골드뱅킹 PDF 파일
│   ├── 200101201204.pdf            # 2020.01.01 ~ 2020.12.04
│   ├── 201205211205.pdf            # 2020.12.05 ~ 2021.12.05
│   ├── 211206221206.pdf            # 2021.12.06 ~ 2022.12.06
│   ├── 221207231207.pdf            # 2022.12.07 ~ 2023.12.07
│   ├── 231208241208.pdf            # 2023.12.08 ~ 2024.12.08
│   └── 241209251209.pdf            # 2024.12.09 ~ 2025.12.09
├── history.json                    # 금시세 데이터 (GitHub Pages로 제공)
└── README.md
```

## Scripts

### update_price.py (일일 업데이트)

매일 실행되어 최신 금시세를 수집하고 history.json을 업데이트합니다.

```bash
# 환경변수 설정 필요
export KRX_API_KEY="your_api_key"

python scripts/update_price.py
```

**데이터 소스:**
- 국제 금시세: Gold-API.com
- 환율: Frankfurter API
- 한국 금시세: 공공데이터포털 (KRX)

### init_history.py (초기화)

LBMA(런던금시장협회) 데이터로 2010년부터의 히스토리를 생성합니다.

```bash
python scripts/init_history.py
```

**주의:** 한국 금시세는 국제 시세 + 3% 프리미엄으로 추정됩니다.

### parse_woori_pdf.py (PDF 파싱 - 미완성)

우리은행 골드뱅킹 PDF에서 금시세 데이터를 추출합니다.

```bash
pip install pdfplumber
python scripts/parse_woori_pdf.py
```

**현재 상태:** PDF가 이미지 기반이라 OCR이 필요합니다. Tesseract + Poppler 설치 후 OCR 로직 추가 필요.

## Data Sources

| 소스 | API | 용도 | 인증 |
|------|-----|------|------|
| Gold-API.com | REST | 국제 금시세 (실시간) | 무료 |
| Frankfurter API | REST | 환율 (USD/KRW) | 불필요 |
| 공공데이터포털 | REST | 한국 금시세 (KRX) | API 키 필요 |
| LBMA | REST | 과거 금시세 (초기화용) | 불필요 |

## Update Schedule

- **자동 업데이트:** 매일 한국시간 오전 9시 (GitHub Actions)
- **데이터 보관:** 최근 90일
- **오래된 데이터:** 자동 삭제

## GitHub Actions

### update-gold-price.yml
- 스케줄: 매일 UTC 00:00 (KST 09:00)
- 작업: update_price.py 실행 → history.json 커밋/푸시

### init-history.yml
- 스케줄: 수동 실행 (workflow_dispatch)
- 작업: init_history.py 실행 → history.json 생성

## 관련 프로젝트

- [gold_widget](https://github.com/taniar88/gold_widget) - 금시세 위젯 Android 앱
