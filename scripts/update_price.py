import json
import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# API URLs
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
KOREAEXIM_API_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
KRX_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
KRX_AJAX_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

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

def get_korean_gold_price_krx_direct(date_str):
    """KRX 직접 API에서 한국 금시세 가져오기 (원/g) - 장 종료 후 사용"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201060201",
            "X-Requested-With": "XMLHttpRequest"
        }

        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT14901",
            "trdDd": date_str.replace("-", "")
        }

        response = requests.post(KRX_AJAX_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        items = result.get("output", [])

        # 금 99.99_1Kg 찾기
        for item in items:
            isu_nm = item.get("ISU_ABBRV", "").lower()
            if "1kg" in isu_nm and "미니" not in isu_nm:
                price_str = str(item.get("TDD_CLSPRC", "0")).replace(",", "")
                return float(price_str)

        # 1Kg 없으면 첫 번째 항목 사용
        if items:
            price_str = str(items[0].get("TDD_CLSPRC", "0")).replace(",", "")
            return float(price_str)

        return None
    except Exception as e:
        print(f"Failed to fetch Korean gold price from KRX direct: {e}")
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
    # 모드 결정: realtime (장 종료 후, 당일 데이터) / daily (오전, 어제 데이터)
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    print(f"Mode: {mode}")

    # API 키 가져오기
    koreadata_api_key = os.environ.get("KOREADATA_API_KEY", "")
    koreaexim_api_key = os.environ.get("KOREAEXIM_API_KEY", "")

    # KST 시간대
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)

    if mode == "realtime":
        # 장 종료 후: 오늘 날짜, KRX 직접 API 사용
        target_date = now_kst.strftime("%Y-%m-%d")
        print(f"Fetching data for: {target_date} (KST: {now_kst.strftime('%Y-%m-%d %H:%M')}) [REALTIME MODE]")
        korean_price = get_korean_gold_price_krx_direct(target_date)
    else:
        # 오전: 어제 날짜, 공공데이터포털 API 사용
        target_date = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"Fetching data for: {target_date} (KST: {now_kst.strftime('%Y-%m-%d %H:%M')}) [DAILY MODE]")
        korean_price = get_korean_gold_price(koreadata_api_key) if koreadata_api_key else None

    # 데이터 가져오기
    international_price = get_international_gold_price()
    exchange_rate = get_exchange_rate(koreaexim_api_key, target_date) if koreaexim_api_key else None

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
        "date": target_date,
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
    existing_index = next((i for i, d in enumerate(history["data"]) if d["date"] == target_date), None)
    if existing_index is not None:
        history["data"][existing_index] = new_entry
        print(f"Updated existing entry for {target_date}")
    else:
        history["data"].append(new_entry)
        print(f"Added new entry for {target_date}")

    # 날짜순 정렬
    history["data"].sort(key=lambda x: x["date"])

    # 업데이트 시간 기록
    history["lastUpdated"] = target_date

    # 저장
    save_history(history)
    print(f"History saved. Total entries: {len(history['data'])}")

if __name__ == "__main__":
    main()
