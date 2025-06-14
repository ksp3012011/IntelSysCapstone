import mojito
from dotenv import load_dotenv
load_dotenv()
import os
import pandas as pd
import ta
import requests
from ta.utils import dropna
import json
import datetime
from datetime import datetime, timedelta

app_key = os.getenv("REAL_APP_KEY")
app_secret= os.getenv("REAL_APP_SECRET")
acc_no = os.getenv("REAL_ACC_NO")

URL_BASE = "https://openapi.koreainvestment.com:9443"

# 액세스 토큰 발급 함수
# 액세스 토큰 발급 함수
def get_cached_token():
    token_file = "kis_token.json"

    # 기존 토큰이 있으면 불러오기
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            token_data = json.load(f)
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            if datetime.now() < expires_at:
                return token_data['access_token']

    # 새 토큰 발급
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    PATH = "/oauth2/tokenP"
    URL = f"{URL_BASE}{PATH}"
    res = requests.post(URL, headers=headers, data=json.dumps(body))
    if res.status_code == 200:
        access_token = res.json()["access_token"]
        expires_at = datetime.now() + timedelta(seconds=3600)
        token_data = {
            "access_token": access_token,
            "expires_at": expires_at.isoformat()
        }
        with open(token_file, 'w') as f:
            json.dump(token_data, f)
        return access_token
    else:
        print("Failed to get access token")
        return None

# time_end를 minutes만큼 줄여주는 함수
def decrease_time(time_str, minutes):
    """time_str을 분 단위로 감소시켜서 새로운 시간을 반환"""
    time_format = '%H%M%S'
    dt = datetime.strptime(time_str, time_format)
    dt -= timedelta(minutes=minutes)
    return dt.strftime(time_format)

# 당일 분봉 OHLCV 데이터 조회 함수
def get_minute_ohlcv_data(access_token, code, time_end="153000"):
    """당일 분봉 OHLCV 데이터를 조회하고 DataFrame으로 반환"""
    PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    URL = f"{URL_BASE}{PATH}"

    all_data = []
   
    # 반복적으로 데이터를 요청하면서 time_end 값을 줄여가며 데이터를 받아옴
    while True:
        # 현재 날짜 설정
        # today = datetime.now().strftime('%Y%m%d')

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appKey": app_key,
            "appSecret": app_secret,
            "tr_id": "FHKST03010200",  # 당일 분봉 데이터 조회용 거래 ID
        }

        params = {
            "FID_ETC_CLS_CODE": "",               # 기타 구분 코드
            "FID_COND_MRKT_DIV_CODE": "J",        # 시장 분류 코드
            "FID_INPUT_ISCD": code,               # 종목 코드
            "FID_INPUT_HOUR_1": time_end,         # 조회 종료 시간 (HHMMSS)
            "FID_PW_DATA_INCU_YN": "N"            # 과거 데이터 포함 여부 (N: 당일만 조회)
        }

        res = requests.get(URL, headers=headers, params=params)
       
        if res.status_code == 200:
            res_data = res.json()
            data = res_data.get('output2', [])
            if data:
                # OHLCV 데이터를 DataFrame으로 변환
                ohlcv_data = [{
                    "Date": item['stck_bsop_date'],  # 거래일자
                    "Time": item['stck_cntg_hour'],  # 체결 시간
                    "Open": item['stck_oprc'],       # 시가
                    "High": item['stck_hgpr'],       # 고가
                    "Low": item['stck_lwpr'],        # 저가
                    "Close": item['stck_prpr'],      # 종가
                    "Volume": item['cntg_vol']       # 체결 거래량
                } for item in data]

                all_data.extend(ohlcv_data)

                # 30개의 데이터를 받았으면 time_end를 줄여서 다음 데이터를 요청
                time_end = decrease_time(time_end, minutes=30)
                print(f"Next time_end: {time_end}")
            else:
                print("No more data available for the specified time.")
                break
        else:
            print(f"Failed to retrieve data: {res.status_code}, {res.text}")
            return None

    # DataFrame 생성 및 정렬
    df = pd.DataFrame(all_data)
    df['DateTime'] = pd.to_datetime(df['Date'] + df['Time'], format='%Y%m%d%H%M%S')  # 날짜와 시간 결합
    df = df.astype({'Open': 'float', 'High': 'float', 'Low': 'float', 'Close': 'float', 'Volume': 'float'})  # 데이터 타입 변환
    df = df[['DateTime', 'Open', 'High', 'Low', 'Close', 'Volume']]  # 열 정렬
    df = df.sort_values(by='DateTime', ascending=True)  # 시간 오름차순 정렬
    df = df.reset_index(drop=True)  # 인덱스를 다시 설정

    # 현재 시간 이후의 데이터 제거
    now = datetime.now()
    df = df[df['DateTime'] <= now]

    # 기술적 지표 추가
    df = ta.utils.dropna(df)
    df['rsi'] = ta.momentum.RSIIndicator(close=df['Close'], window=14).rsi()
    df['sma_10'] = ta.trend.SMAIndicator(close=df['Close'], window=10).sma_indicator()
    df['sma_30'] = ta.trend.SMAIndicator(close=df['Close'], window=30).sma_indicator()

    # 60개만 받아오기
    df = df.tail(60).reset_index(drop=True)
    return df

# 메인 실행 부분
if __name__ == "__main__":
    access_token = get_cached_token()
    if access_token:

        # 종목, 조회 종료 시간 지정 (예: 15:30:00까지 데이터를 받아오기 시작)
        code_stock_krx = '005930'
        time_end = "153000"     # 종료 시간

        df = get_minute_ohlcv_data(access_token, code=code_stock_krx, time_end=time_end)
        if df is not None:
            print(df)
    else:
        print("Failed to get access token.")
