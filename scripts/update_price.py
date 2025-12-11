import json
import os
import requests
from datetime import datetime, timedelta

# API URLs
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
KOREAEXIM_API_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
KRX_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"

def get_international_gold_price():
    """Gold-API.com에서 국제 금시세 가져오기 (USD/oz)"""
    try:
        response = requests.get(GOLD_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("price", 0)
    except Exception as e:
        print(f"Failed to fetch international gold price: {e}")
        return None

def get_exchange_rate(api_key, date_str):
    """한국수출입은행 API에서 환율 가져오기 (USD/KRW 매매기준율)"""
    try:
        params = {
            "authkey": api_key,
            "searchdate": date_str,
            "data": "AP01"
        }
        response = requests.get(KOREAEXIM_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # USD 환율 찾기
        for item in data:
            if item.get("cur_unit") == "USD":
                # 매매기준율에서 콤마 제거 후 float 변환
                rate_str = item.get("deal_bas_r", "0").replace(",", "")
                return float(rate_str)

        return None
    except Exception as e:
        print(f"Failed to fetch exchange rate: {e}")
        return None

def get_korean_gold_price(api_key):
    """공공데이터포털에서 한국 금시세 가져오기 (원/g)"""
    try:
        params = {
            "serviceKey": api_key,
            "numOfRows": 5,
            "resultType": "json"
        }
        response = requests.get(KRX_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        # 1kg 금 데이터 찾기 (상품명: "금 99.99_1Kg")
        for item in items:
            itms_nm = item.get("itmsNm", "").lower()
            if "1kg" in itms_nm and "미니" not in itms_nm:
                # clpr은 이미 원/g 단위
                return float(item.get("clpr", 0))

        # 1kg 없으면 첫 번째 항목 사용 (clpr은 원/g 단위)
        if items:
            return float(items[0].get("clpr", 0))

        return None
    except Exception as e:
        print(f"Failed to fetch Korean gold price: {e}")
        return None

def load_history():
    """기존 히스토리 파일 로드"""
    try:
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"lastUpdated": "", "data": []}

def save_history(history):
    """히스토리 파일 저장"""
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def main():
    print("Fetching gold price data...")

    # API 키 가져오기
    krx_api_key = os.environ.get("KRX_API_KEY", "")
    koreaexim_api_key = os.environ.get("KOREAEXIM_API_KEY", "")

    # 어제 날짜 (확정된 데이터 사용)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"Fetching data for: {yesterday}")

    # 데이터 가져오기
    international_price = get_international_gold_price()
    exchange_rate = get_exchange_rate(koreaexim_api_key, yesterday) if koreaexim_api_key else None
    korean_price = get_korean_gold_price(krx_api_key) if krx_api_key else None

    print(f"International price: {international_price} USD/oz")
    print(f"Exchange rate: {exchange_rate} KRW/USD")
    print(f"Korean price: {korean_price} KRW/g")

    # 데이터 유효성 확인
    if international_price is None or exchange_rate is None:
        print("Failed to fetch required data. Skipping update.")
        return

    # 한국 금시세가 없으면 추정값 사용
    if korean_price is None or korean_price == 0:
        korean_price = (international_price / 31.1035) * exchange_rate * 1.03
        print(f"Using estimated Korean price: {korean_price} KRW/g")

    # 국제 금시세를 원/g로 변환
    international_price_krw = (international_price / 31.1035) * exchange_rate

    # 프리미엄 계산
    premium = ((korean_price - international_price_krw) / international_price_krw) * 100 if international_price_krw > 0 else 0

    # 새 데이터
    new_entry = {
        "date": yesterday,
        "koreanPrice": round(korean_price, 2),
        "internationalPrice": round(international_price, 2),
        "internationalPriceKrw": round(international_price_krw, 2),
        "exchangeRate": round(exchange_rate, 2),
        "premium": round(premium, 2)
    }

    print(f"New entry: {new_entry}")

    # 히스토리 로드
    history = load_history()

    # 해당 날짜 데이터가 이미 있으면 업데이트, 없으면 추가
    existing_index = next((i for i, d in enumerate(history["data"]) if d["date"] == yesterday), None)
    if existing_index is not None:
        history["data"][existing_index] = new_entry
        print(f"Updated existing entry for {yesterday}")
    else:
        history["data"].append(new_entry)
        print(f"Added new entry for {yesterday}")

    # 날짜순 정렬
    history["data"].sort(key=lambda x: x["date"])

    # 업데이트 시간 기록
    history["lastUpdated"] = yesterday

    # 저장
    save_history(history)
    print(f"History saved. Total entries: {len(history['data'])}")

if __name__ == "__main__":
    main()
