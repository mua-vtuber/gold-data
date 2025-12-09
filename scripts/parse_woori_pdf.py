"""
우리은행 골드뱅킹 PDF에서 금시세 데이터 추출
PDF 파일: F:\hayoung\git\금시세\*.pdf
출력: history.json
"""
import json
import os
import re
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("pdfplumber가 설치되어 있지 않습니다.")
    print("설치 명령어: pip install pdfplumber")
    exit(1)

# PDF 파일 경로
PDF_DIR = r"F:\hayoung\git\금시세"

def parse_date(date_str):
    """날짜 파싱 (YYYY.MM.DD -> YYYY-MM-DD)"""
    try:
        # 2025.12.09 형식
        parts = date_str.strip().split('.')
        if len(parts) == 3:
            year, month, day = parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        pass
    return None

def parse_number(num_str):
    """숫자 파싱 (콤마 제거)"""
    try:
        # 콤마 제거하고 float 변환
        cleaned = num_str.replace(',', '').strip()
        return float(cleaned)
    except:
        return None

def extract_data_from_pdf(pdf_path):
    """PDF 파일에서 데이터 추출"""
    data = []

    print(f"Processing: {os.path.basename(pdf_path)}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # 테이블 추출
                tables = page.extract_tables()

                for table in tables:
                    for row in table:
                        if not row or len(row) < 6:
                            continue

                        # 첫 번째 열이 날짜인지 확인 (YYYY.MM.DD 형식)
                        first_cell = str(row[0]).strip() if row[0] else ""

                        # 날짜 패턴 확인
                        if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', first_cell):
                            continue

                        try:
                            date = parse_date(row[0])
                            if not date:
                                continue

                            # 컬럼: 일자, 기준가격, 매입가격, 매도가격, 금가격(USD), 원달러환율
                            korean_price = parse_number(row[1])  # 기준가격(원/g)
                            intl_price_usd = parse_number(row[4])  # 금가격(USD/트로이온즈)
                            exchange_rate = parse_number(row[5])  # 원달러환율

                            if korean_price and intl_price_usd and exchange_rate:
                                # 국제 금시세를 원/g로 변환
                                intl_price_krw = (intl_price_usd / 31.1035) * exchange_rate

                                # 프리미엄 계산
                                premium = ((korean_price - intl_price_krw) / intl_price_krw) * 100 if intl_price_krw > 0 else 0

                                data.append({
                                    "date": date,
                                    "koreanPrice": round(korean_price, 2),
                                    "internationalPrice": round(intl_price_usd, 2),
                                    "internationalPriceKrw": round(intl_price_krw, 2),
                                    "exchangeRate": round(exchange_rate, 2),
                                    "premium": round(premium, 2)
                                })
                        except Exception as e:
                            continue

    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")

    return data

def main():
    all_data = []

    # PDF 파일 목록
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]
    print(f"Found {len(pdf_files)} PDF files")

    for pdf_file in sorted(pdf_files):
        pdf_path = os.path.join(PDF_DIR, pdf_file)
        data = extract_data_from_pdf(pdf_path)
        all_data.extend(data)
        print(f"  -> Extracted {len(data)} records")

    # 중복 제거 (날짜 기준)
    unique_data = {}
    for item in all_data:
        unique_data[item["date"]] = item

    # 날짜순 정렬
    sorted_data = sorted(unique_data.values(), key=lambda x: x["date"])

    print(f"\nTotal unique records: {len(sorted_data)}")

    if sorted_data:
        print(f"Date range: {sorted_data[0]['date']} ~ {sorted_data[-1]['date']}")

    # history.json 저장
    history = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "data": sorted_data
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "history.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")

if __name__ == "__main__":
    main()
