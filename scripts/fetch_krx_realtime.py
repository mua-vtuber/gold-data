import json
import os
import requests
from datetime import datetime, timedelta, timezone

# KRX 데이터센터 AJAX API (실시간)
KRX_AJAX_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

def get_krx_gold_price():
    """KRX 데이터센터 AJAX API에서 금 시세 가져오기 (실시간)"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201060201",
            "X-Requested-With": "XMLHttpRequest"
        }

        # 오늘 날짜 (KST 기준)
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).strftime("%Y%m%d")

        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT14901",
            "trdDd": today
        }

        response = requests.post(KRX_AJAX_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()

        result = response.json()
        print(f"KRX AJAX response: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}")

        # output에서 금 데이터 찾기
        items = result.get("output", [])

        # 금 99.99_1Kg 찾기
        for item in items:
            isu_nm = item.get("ISU_ABBRV", "")
            if "1kg" in isu_nm.lower() and "미니" not in isu_nm.lower():
                return parse_krx_item(item, today)

        # 1Kg 없으면 첫 번째 항목 사용
        if items:
            return parse_krx_item(items[0], today)

        return None
    except Exception as e:
        print(f"Failed to fetch KRX gold price: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_krx_item(item, today):
    """KRX AJAX 응답 항목 파싱"""
    def safe_float(val):
        if not val:
            return 0.0
        # 콤마 제거하고 숫자로 변환
        clean_val = str(val).replace(",", "")
        try:
            return float(clean_val)
        except ValueError:
            return 0.0

    return {
        "name": item.get("ISU_ABBRV", ""),
        "price": safe_float(item.get("TDD_CLSPRC", 0)),  # 현재가/종가
        "change": safe_float(item.get("CMPPREVDD_PRC", 0)),  # 전일대비
        "changePercent": safe_float(item.get("FLUC_RT", 0)),  # 등락률
        "high": safe_float(item.get("TDD_HGPRC", 0)),  # 고가
        "low": safe_float(item.get("TDD_LWPRC", 0)),  # 저가
        "volume": str(item.get("ACC_TRDVOL", "0")).replace(",", ""),  # 거래량
        "date": today
    }

def get_international_gold_price():
    """Gold-API.com에서 국제 금시세 가져오기 (USD/oz)"""
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("price", 0)
    except Exception as e:
        print(f"Failed to fetch international gold price: {e}")
        return None

def get_exchange_rate():
    """Frankfurter API에서 환율 가져오기"""
    try:
        response = requests.get("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("rates", {}).get("KRW", 1400)
    except Exception as e:
        print(f"Failed to fetch exchange rate: {e}")
        return 1400  # 기본값

def main():
    # KST 시간대
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    print(f"Fetching realtime gold price at {now_kst.isoformat()}")

    # 데이터 가져오기
    krx_data = get_krx_gold_price()
    international_price = get_international_gold_price()
    exchange_rate = get_exchange_rate()

    print(f"KRX data: {krx_data}")
    print(f"International price: {international_price} USD/oz")
    print(f"Exchange rate: {exchange_rate} KRW/USD")

    # 한국 금시세
    korean_price = krx_data["price"] if krx_data else 0
    korean_change = krx_data["change"] if krx_data else 0
    korean_change_percent = krx_data["changePercent"] if krx_data else 0

    # 국제 금시세를 원/g로 변환
    international_price_krw = (international_price / 31.1035) * exchange_rate if international_price else 0

    # 프리미엄 계산
    premium = 0
    if international_price_krw > 0 and korean_price > 0:
        premium = ((korean_price - international_price_krw) / international_price_krw) * 100

    # 결과 저장
    result = {
        "lastUpdated": now_kst.isoformat(),
        "korean": {
            "price": round(korean_price, 2),
            "change": round(korean_change, 2),
            "changePercent": round(korean_change_percent, 2),
            "source": "KRX" if krx_data else "estimated"
        },
        "international": {
            "priceUsd": round(international_price, 2) if international_price else 0,
            "priceKrw": round(international_price_krw, 2)
        },
        "exchangeRate": round(exchange_rate, 2),
        "premium": round(premium, 2)
    }

    print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

    # 파일 저장
    with open("realtime.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("Saved to realtime.json")

if __name__ == "__main__":
    main()
