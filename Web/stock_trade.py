from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
import os
import requests
import json
import mojito
import ta
import sqlite3
import schedule
import time
import pprint
from smtp import send_email, send_trade, send_paper
from sql import get_user_settings, get_all_emails

app_key = os.getenv("REAL_APP_KEY")
app_secret= os.getenv("REAL_APP_SECRET")
acc_no = os.getenv("REAL_ACC_NO")

URL_BASE = "https://openapi.koreainvestment.com:9443"

# 데이터베이스 초기화
def init_database():
    conn = sqlite3.connect('stock_trading.db')
    cursor = conn.cursor()
    
    # 거래 내역 테이블 생성
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        timestamp TEXT,
        decision TEXT,
        reason TEXT,
        hold_quantity INTEGER,
        trading_quantity INTEGER,
        remaining_cash REAL,
        current_value REAL,
        purchase_amount REAL
    )
    ''')
    
    conn.commit()
    conn.close()


# 거래 내역 저장
def save_trade(symbol, decision, reason, trading_quantity, code):
    # 현재 시간
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # 브로커에서 계좌 정보 가져오기
        time.sleep(0.5)
        broker = load_broker()
        balance_info = broker.fetch_balance()
        
        # 계좌 잔고 정보
        remaining_cash = float(balance_info['output2'][0]['dnca_tot_amt'])  # 예수금

        current_value = 0.0
        purchase_amount = 0.0
        hold_quantity = 0.0

        # 종목별 정보 가져오기 (보유 종목에서 현재 종목 찾기)
        if 'output1' in balance_info and balance_info['output1']:
            for item in balance_info['output1']:
                if item.get('pdno') == code:  # 종목코드 비교
                    current_value = float(item['evlu_amt'])  # 평가 금액
                    hold_quantity = float(item['hldg_qty']) # 보유 수량
                    purchase_amount = float(item['pchs_amt'])  # 매입 금액
                    break
        
        # DB에 저장
        conn = sqlite3.connect('stock_trading.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO trades (symbol, timestamp, decision, reason, hold_quantity, trading_quantity, remaining_cash, current_value, purchase_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, timestamp, decision, reason, hold_quantity, trading_quantity, remaining_cash, current_value, purchase_amount))
        
        conn.commit()
        conn.close()
        
        print(f"거래 내역이 데이터베이스에 저장되었습니다: {symbol}, {decision}, {trading_quantity}주")
        
    except Exception as e:
        print(f"거래 내역 저장 중 오류 발생: {e}")


def load_broker():

    # 모의 계좌 매매(장 시간 끝나면 분봉 데이터 못 불러옴)
    app_key = os.getenv("MOC_APP_KEY")
    app_secret= os.getenv("MOC_APP_SECRET")
    acc_no = os.getenv("MOC_ACC_NO")


    broker = mojito.KoreaInvestment(
    api_key=app_key,
    api_secret=app_secret,
    acc_no=acc_no,
    mock=True   # 모의 계좌시 필요
    )

    return broker

# 코스피 종목 기준 시가 총액이 가장 높은 10개 종목
def get_top_kospi_stocks(n=10):
    today = datetime.today()
    today_str = today.strftime('%Y%m%d')
    latest_date = stock.get_nearest_business_day_in_a_week(today_str)

    cap_df = stock.get_market_cap_by_ticker(latest_date, market='KOSPI')
    cap_df['종목명'] = [stock.get_market_ticker_name(code) for code in cap_df.index]
    cap_df['종목코드'] = cap_df.index
    cap_df.set_index('종목명', inplace=True)
    top_stocks = cap_df.sort_values(by='시가총액', ascending=False).head(n)
    return top_stocks

# 종목 관련 뉴스 헤드라인
def get_news(keyword):
    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': keyword,
        'pageSize': 3,
        'language': 'ko',
        'sortBy': 'publishedAt',
        'apiKey': os.getenv('NEWS_API')
    }
    response = requests.get(url, params=params)
    return response.json()

# 종목별 5년간의 재무 지표, 최신 뉴스 헤드라인 저장
def build_analysis_data(top_stocks):
    today = datetime.today()
    start_date = (today - timedelta(days=365 * 5)).replace(month=1, day=1)
    year = today.replace(month=1, day=1)

    analysis_data = []
    for name, row in top_stocks.iterrows():
        code = row['종목코드']

        # 종목별 5년치의 재무 지표 가져오기
        fundamentals = stock.get_market_fundamental(start_date, year, code, freq="y")

        # 종목별 최신 뉴스 헤드라인 3개 가져오기
        news_json = get_news(name)
        news_titles = [article['title'] for article in news_json.get('articles', []) if news_json.get('status') == 'ok']

        analysis_data.append({
            'name': name,
            'code': code,
            'fundamentals': fundamentals.reset_index().to_dict(orient='records'),
            'news': news_titles
        })
    return analysis_data

client = OpenAI()

# 종목 추천 
def get_recommendations(analysis_data):
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """
                당신은 주식 종목을 추천해주는 전문가입니다.
                다음은 한국 KOSPI 시가총액 상위 10개 종목의 최근 5년치 연간 재무 지표와 관련 최신 뉴스 제목입니다.
                이 정보를 종합 분석하여 향후 주가 상승 가능성이 높은 3개의 종목을 추천해주세요. 
                선정 근거도 함께 설명해 주세요.
                응답은 반드시 JSON 형식으로 작성하며, 다음과 같은 구조를 따라야 합니다:
                {
                  "recommendations": [
                    {"name": "종목명"},
                    ...
                  ]
                }
                """
            },
            {
                "role": "user",
                "content": json.dumps(analysis_data, ensure_ascii=False, default=str)
            }
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


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
    time.sleep(0.5)
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
def get_minute_ohlcv_data(access_token, code, time_end):
    """당일 분봉 OHLCV 데이터를 조회하고 DataFrame으로 반환"""
    PATH = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    URL = f"{URL_BASE}{PATH}"

    all_data = []
   
    # 반복적으로 데이터를 요청하면서 time_end 값을 줄여가며 데이터를 받아옴
    while True:
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

        time.sleep(0.5)
       
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
                time.sleep(0.5)
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

    df = df.tail(60).reset_index(drop=True)
    return df


def get_day_ohlcv_data(broker, code):
    time.sleep(0.5)
    resp = broker.fetch_ohlcv(
    symbol=code,
    timeframe='D',
    adj_price=True
    )

    time.sleep(0.5)

    df = pd.DataFrame(resp['output2'])
    dt = pd.to_datetime(df['stck_bsop_date'], format="%Y%m%d")
    df.set_index(dt, inplace=True)
    df = df[['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_clpr']]
    df.columns = ['open', 'high', 'low', 'close']
    df.index.name = "date"
    df
    df = df[::-1]

    return df


strategy_path = "./stock_strategy/strategy.txt"
with open(strategy_path, "r", encoding="utf-8") as file:
        strategy_text = file.read()

def get_trade_decision(symbol, strategy_text, minute_df, hour_df):
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """
                당신은 한국 주식시장에서 기술적 분석을 통해 매매 판단을 내리는 전문가입니다.
                주어진 전략을은 분봉 데이터에만 적용하고 일봉은 추세를 파악에만 사용하여 분석 후 매수(buy), 매도(sell), 보유(hold) 중 하나를 선택.

                응답은 반드시 JSON 형식으로 작성. 예시:
                {"symbol": "종목명", "decision": "buy", "confidence": 0~10, "reason": "판단 이유"}
                {"symbol": "종목명", "decision": "sell", "confidence": 0~10, "reason": "판단 이유"}
                {"symbol": "종목명", "decision": "hold", "confidence": 0, "reason": "판단 이유"}

                confidence는 확신도를 의미하며, 0~10 사이의 숫자입니다.
                decision이 hold일 경우 confidence는 반드시 0이어야 합니다.
                reason은 반드시 한글로 서술하며, 분석에 기반한 설명을 포함해야 합니다.
                """
            },
            {
                "role": "user",
                "content": f"""전략: {strategy_text}
                분봉 데이터 (symbol={symbol}): {minute_df.to_json(date_format='iso', orient='records')}
                일봉 데이터 (symbol={symbol}): {hour_df.to_json(date_format='iso', orient='records')}
                """
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)

# 실제 거래소에서 매매
def execute_trade(broker, decision, code, email):
    # 종목명으로 코드 추출
    name = decision.get("symbol")
    decision_type = decision.get("decision")
    quantity = decision.get("confidence", 0)
    reason = decision.get("reason", "")

    # 계좌 정보 조회
    balance_info = broker.fetch_balance()
    time.sleep(0.5)

    output1 = balance_info.get('output1', [])
    output2 = balance_info.get('output2', [])

    remaining_cash = float(output2[0]['dnca_tot_amt']) if output2 else 0.0

   
    # 현재 종목의 보유 수량 및 현재가 확인
    current_holding = 0
    current_price = 0

    # 보유 종목 확인
    if 'output1' in balance_info and balance_info['output1']:
        for item in balance_info['output1']:
            if item['pdno'] == code:  # 종목코드 비교
                current_holding = int(item['hldg_qty'])  # 보유수량
                break
   
    # 매수
    if decision_type == "buy":
        # 현재가 확인
        price_info = broker.fetch_price(code)
        time.sleep(0.5)
        current_price = float(price_info['output']['stck_prpr'])  # 현재가
        total_cost = current_price * quantity
        
        # 예수금이 부족한 경우
        if total_cost > remaining_cash:
            print(f"[매수 실패] {name} ({code}) - 금액이 부족합니다. 필요: {total_cost:.0f}원, 보유: {remaining_cash:.0f}원")
            save_trade(name, "buy_failed", f"{reason} (금액 부족)", 0, code)
        else:
            print(f"[매수 시도] {name} ({code}) - {quantity}주 (총 {total_cost:.0f}원)")
            resp = broker.create_market_buy_order(symbol=code, quantity=quantity)  # 실제 매수
            pprint.pprint(resp)
            time.sleep(5) # market_buy/sell 직후 fetch_balance() 실행시 오류나기 때문에 지연 시간 추가 
            save_trade(name, "buy", reason, quantity, code)
            #메일 전송
            send_trade(email, name, quantity, total_cost, "매수")

    # 매도
    elif decision_type == "sell":
        # 팔려고 하는 개수가 현재 보유한 개수보다 많을 경우
        if quantity > current_holding:
            if current_holding > 0:
                print(f"[매도 조정] {name} ({code}) - 요청: {quantity}주, 보유: {current_holding}주, {current_holding}주만 매도합니다.")
                # 현재 보유한 개수만큼 판매
                quantity = current_holding
                resp = broker.create_market_sell_order(symbol=code, quantity=quantity) # 실제 매도
                pprint.pprint(resp)
                time.sleep(5) # market_buy/sell 직후 fetch_balance() 실행시 오류나기 때문에 지연 시간 추가
                save_trade(name, "sell", f"{reason} (보유 수량으로 조정)", quantity, code)
                #메일 전송
                send_trade(email, name, quantity, total_cost, "매도")
            else:
                print(f"[매도 실패] {name} ({code}) - 보유 수량이 없습니다.")
                save_trade(name, "sell_failed", f"{reason} (보유 수량 없음)", 0, code)
        else:
            print(f"[매도 시도] {name} ({code}) - {quantity}주")
            resp = broker.create_market_sell_order(symbol=code, quantity=quantity) # 실제 매도
            pprint.pprint(resp)
            time.sleep(5) # market_buy/sell 직후 fetch_balance() 실행시 오류나기 때문에 지연 시간 추가
            save_trade(name, "sell", reason, quantity, code)
            #메일 전송
            send_trade(email, name, quantity, total_cost, "매도")
            
    # 보유
    elif decision_type == "hold":
        print(f"[보유 판단] {name} ({code}) - 아무 행동 없음")
        save_trade(name, "hold", reason, 0, code)


RECOMMENDED_STOCKS = []

def auto_stock_trading():

    user_setting = get_user_settings("ksp3012011@gmail.com")
    if user_setting['stock_auto'] == 0:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 주식 자동매매가 비활성화되어 있습니다. 주식 자동매매를 건너뜁니다.")
        return
    
    if not is_market_open():
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 장이 닫혔거나 주말입니다. 주식 자동매매를 건너뜁니다.")
        return
    
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 주식 자동매매 실행 중...")

    broker = load_broker()
    access_token = get_cached_token()
    time_end = "153000"

    user_email = get_all_emails()
    for email in user_email:
        # 이메일로 사용자 설정 가져오기
        setting_data = get_user_settings(email)
        if setting_data['stock_auto'] == 0:
            continue

        # 저장된 3 종목들에 대해 매매 판단 및 실행
        for stock_info in RECOMMENDED_STOCKS:
            name = stock_info['name']
            code = stock_info['code']
            try:
                print(f"\n추천 종목: {name} ({code})")
                minute_df = get_minute_ohlcv_data(access_token, code, time_end=time_end)
                time.sleep(0.5)
                day_df = get_day_ohlcv_data(broker, code)
                time.sleep(0.5)

                decision = get_trade_decision(name, strategy_text, minute_df, day_df)
                print(f"매매 판단: {decision['decision']} (확신도: {decision['confidence']})")
                print(f"사유: {decision['reason']}\n")

                execute_trade(broker, decision, code, email)

                time.sleep(0.5)

            except Exception as e:
                print(f"{name}의 데이터를 가져오는 데 실패했습니다: {e}")


def is_market_open():
    """현재 시간이 주식 시장 거래 시간(9:00-15:30)인지 확인"""
    now = datetime.now()
    current_time = dt_time(now.hour, now.minute)
    
    # 주말 체크
    if now.weekday() >= 5:  # 5: 토요일, 6: 일요일
        return False
    
    # 장 시간 체크 (9:00 ~ 15:30)
    market_start = dt_time(9, 0)
    market_end = dt_time(15, 30)
    
    return market_start < current_time < market_end

init_database()

def recommend_stock():

    # 이미 추천 종목이 있다면 다시 추천하지 않음
    if not RECOMMENDED_STOCKS:
        top_stocks = get_top_kospi_stocks(10)
        analysis_data = build_analysis_data(top_stocks)
        recommendation_result = get_recommendations(analysis_data)
        recommendations = recommendation_result.get("recommendations", [])

        for stock_info in recommendations:
            name = stock_info['name']
            try:
                code = top_stocks.loc[name]['종목코드']
                stock_info['code'] = code
                RECOMMENDED_STOCKS.append(stock_info)
            except Exception as e:
                print(f"{name} 종목코드 조회 실패: {e}")

        print("추천 종목 3개가 설정되었습니다.")
        
