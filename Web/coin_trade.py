import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
import pyupbit
import ta
import requests
from ta.utils import dropna
import json
import pandas as pd
import time
from datetime import datetime
import sqlite3
import schedule

# 공포 탐욕 지수
def get_fear_and_greed_index():
    url = "https://api.alternative.me/fng/"
    response = requests.get(url)
        
    if response.status_code == 200:
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            index_value = data["data"][0]["value"]
            index_classification = data["data"][0]["value_classification"]
            return {
                "fear_and_greed_index": index_value,
                "fear_or_greed": index_classification
            }
        
    return {"error": "Failed to fetch data"}


# News API 엔드포인트 및 API 키 설정
url = 'https://newsapi.org/v2/everything'


# 비트코인 관련 뉴스 불러오기
def get_news(category):
    params = {
        'q': category,  # 원하는 뉴스
        'pageSize': 5,
        'language': 'en',
        'sortBy': 'publishedAt',
        'apiKey': os.getenv('NEWS_API')  # 발급받은 API 키
    }
    response = requests.get(url, params=params)
    data = response.json()

    return data

def news():
    
    news_object = get_news('BTC')
    news_data = []

    # 최신 비트코인 뉴스 5가지
    if news_object['status'] == 'ok':
        for i, article in enumerate(news_object['articles'], start=1):
            title = article['title']

            news_data.append({
                'title': title
            })

    else:
        print("뉴스를 불러오는 데 문제가 발생했습니다.")

    return news_data


# SQLite 데이터베이스 초기화 함수
def init_db():
    conn = sqlite3.connect('bitcoin_trading.db')
    cursor = conn.cursor()
    
    # 거래 기록 테이블 생성
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        timestamp TEXT,
        decision TEXT,
        reason TEXT,
        btc_balance REAL,
        krw_balance REAL,
        btc_krw_price REAL,
        profit_rate REAL,
        income REAL
    )
    ''')
    
    conn.commit()
    conn.close()


# 거래 기록 저장 함수
def save_trade(decision, reason):
    conn = sqlite3.connect('bitcoin_trading.db')
    cursor = conn.cursor()
    
    symbol = "BTC"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    krw_balance = upbit.get_balance("KRW")
    btc_balance = upbit.get_balance("KRW-BTC")
    btc_krw_price = pyupbit.get_current_price("KRW-BTC") 
    income, profit_rate = calculate_profit()
    
    
    cursor.execute('''
    INSERT INTO trades (timestamp, symbol, decision, reason, btc_balance, krw_balance, btc_krw_price, profit_rate, income)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, symbol, decision, reason, btc_balance, krw_balance, btc_krw_price, profit_rate, income))
    
    conn.commit()
    conn.close()


def load_trades():
    conn = sqlite3.connect('bitcoin_trading.db')
    df = pd.read_sql_query("SELECT * FROM trades", conn)
    conn.close()
    return df


init_db()

# 초기 투자 금액 계산 함수
def calculate_initial_investment(df):
    initial_krw_balance = df.iloc[0]['krw_balance']
    initial_btc_balance = df.iloc[0]['btc_balance']
    initial_btc_price = df.iloc[0]['btc_krw_price']
    initial_total_investment = initial_krw_balance + (initial_btc_balance * initial_btc_price)
    return initial_total_investment

# 현재 투자 금액 계산 함수
def calculate_current_investment(df):
    current_krw_balance = df.iloc[-1]['krw_balance']
    current_btc_balance = df.iloc[-1]['btc_balance']
    current_btc_price = pyupbit.get_current_price("KRW-BTC")  # 현재 BTC 가격 가져오기
    current_total_investment = current_krw_balance + (current_btc_balance * current_btc_price)
    return current_total_investment

# 수익률, 손익 계산 함수
def calculate_profit():

    df = load_trades()

    # 첫 거래라 DB가 비어 있을 경우
    if df.empty:
        return 0, 0

    # 초기 투자 금액 계산
    initial_investment = calculate_initial_investment(df)

    # 현재 투자 금액 계산
    current_investment = calculate_current_investment(df)

    # 원화 손익 계산
    income = current_investment - initial_investment

    # 수익률 계산
    profit_rate = ( income / initial_investment) * 100 

    return income, profit_rate


# Upbit 객체 생성
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
if not access or not secret:
    raise ValueError("Missing API keys. Please check your .env file.")
upbit = pyupbit.Upbit(access, secret)


path = "./strategy/"

# txt 파일 리스트
strategy_paths = [f"{path}strategy{i}.txt" for i in range(1, 4)]

# 각 전략별 필요한 기술적 지표 매핑
strategy_indicators = {
    "strategy1.txt": ["atr"],                       # 변동성 수축 패턴 사용 전략
    "strategy2.txt": ["bollinger_bands"],           # 볼린저 밴드 스퀴즈 전략1                             # 볼린저 밴드 스퀴즈 전략2
    "strategy3.txt": ["stockastic_rsi"],     # 히아킨 애쉬 전략 
}


# 전략 파일명에서 파일 이름만 추출하는 함수
def get_strategy_filename(strategy_paths):
    return os.path.basename(strategy_paths)


# heikin-ashi 변환
def heikin_ashi(df):
    df_ha = df.copy()
    df_ha['close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

    for i in range(len(df)):
        if i == 0:
            df_ha.iat[0, df.columns.get_loc('open')] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
        else:
            df_ha.iat[i, df.columns.get_loc('open')] = (df_ha.iat[i-1, df.columns.get_loc('open')] + df_ha.iat[i-1, df.columns.get_loc('close')]) / 2

    # Heikin-Ashi high/low
    df_ha['high'] = df_ha.loc[:, ['open', 'close']].join(df['high']).max(axis=1)
    df_ha['low'] = df_ha.loc[:, ['open', 'close']].join(df['low']).min(axis=1)

    return df_ha


def calculate_indicators(df, best_match):
    file_name = get_strategy_filename(best_match)
    indicators = strategy_indicators.get(file_name, [])

    # 1. 기본값: 원본 OHLCV
    use_heikin_ashi = "stockastic_rsi" in indicators
    working_df = heikin_ashi(df) if use_heikin_ashi else df.copy()  # OHLCV 소스 결정

    # 2. 결과 DataFrame 초기화 (OHLCV 컬럼만 복사)
    result_df = working_df[['open', 'high', 'low', 'close', 'volume']].copy()

    # 3. 지표 추가
    for indicator in indicators:
        if indicator == "atr":
            tr1 = abs(df['high'] - df['low'])
            tr2 = abs(df['close'].shift(1) - df['high'])
            tr3 = abs(df['close'].shift(1) - df['low'])
            trs = pd.concat([tr1, tr2, tr3], axis=1)
            atr = trs.max(axis=1).rolling(window=14).mean()
            result_df['ATR'] = atr

        elif indicator == "bollinger_bands":
            bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
            result_df['bb_bbh'] = bb.bollinger_hband()
            result_df['bb_bbm'] = bb.bollinger_mavg()
            result_df['bb_bbl'] = bb.bollinger_lband()
            result_df['bb_width'] = (result_df['bb_bbh'] - result_df['bb_bbl']) / result_df['bb_bbm']

        elif indicator == "stockastic_rsi":
            working_df['rsi'] = ta.momentum.RSIIndicator(close=working_df['close'], window=14).rsi()
            min_rsi = working_df['rsi'].rolling(window=14).min()
            max_rsi = working_df['rsi'].rolling(window=14).max()
            stoch_rsi = 100 * (working_df['rsi'] - min_rsi) / (max_rsi - min_rsi)
            result_df['k'] = stoch_rsi.rolling(window=3).mean()
            result_df['d'] = result_df['k'].rolling(window=3).mean()

    return result_df


client = OpenAI()

# 전략별 매매 판단
def strategy_agent(strategy_path, df_15minute, df_hourly, orderbook):

    # 전략 내용 로딩
    with open(strategy_path, "r", encoding="utf-8") as file:
        strategy_text = file.read()

    # 지표 계산
    df_15minute = calculate_indicators(df_15minute.copy(), strategy_path)

    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """당신은 특정 비트코인 전략 분석 에이전트입니다. 주어진 전략에 따라 기술적 분석을 수행하고 매매 판단을 JSON 형식으로 응답.
                
                주어진 투자 전략을 기반으로 15분봉, 기술적 지표, 호가창을 분석.
                투자 전략은 15분봉에만 적용하고, 시간봉은 추세 파악에만 사용.
                판단 이유는 한글로 작성
                응답은 반드시 JSON 형식으로 다음과 같이 작성:
                {"decision": "buy", "percentage": 0~100, "reason": "판단 이유"}
                {"decision": "sell", "percentage": 0~100, "reason": "판단 이유"}
                {"decision": "hold", "percentage": 0, "reason": "판단 이유"}
                """
            },
            {
                "role": "user",
                "content": f"""전략: {strategy_text}
                5분봉 데이터: {df_15minute.to_json()}
                시간봉 데이터: {df_hourly.to_json()}
                호가창: {json.dumps(orderbook)}
                """
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)

# 시장 심리 분석 Agent
def market_sentiment_agent(news_data, fear_greed_index):
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """당신은 시장 심리 분석 에이전트입니다. 뉴스 및 공포탐욕지수를 바탕으로 시장 방향을 판단.
                뉴스 데이터와 공포 탐욕 지수를 분석해서 현재 시장이 어떤지 한글로 설명.
                현재 시장 파악과 방향성 설명만 출력하고 뉴스 헤드라인은 반드시  출력하지 말 것.
                응답은 반드시 JSON 형식으로 작성
                """
            },
            {
                "role": "user",
                "content": f"""공포탐욕지수: {json.dumps(fear_greed_index)}
                뉴스: {json.dumps(news_data)}
                """
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)


def final_decision_agent(agent_outputs):
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": """당신은 최종 판단 에이전트입니다. 여러 전략 및 심리 판단 결과를 종합해 최종 매매 결정을 내리세요.
                판단 이유는 한글로 설명
                응답은 반드시 JSON 형식으로 다음과 같이 작성:
                {"decision": "buy", "percentage": 0~100, "reason": "판단 이유"}
                {"decision": "sell", "percentage": 0~100, "reason": "판단 이유"}
                {"decision": "hold", "percentage": 0, "reason": "판단 이유"}
                """
            },
            {
                "role": "user",
                "content": f"""에이전트들의 판단 결과: {json.dumps(agent_outputs, indent=2)}"""
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)

# 실제 거래소 매매
def execute_trade(result):
    charge = 0.9995
    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        buy_amount = my_krw * (result["percentage"] / 100) * charge
        if buy_amount > 5000:   # 최소 주문 금액 5000krw
            # upbit.buy_market_order("KRW-BTC", buy_amount)   # 실제 거래소에서 매매
            save_trade("buy", result["reason"])
        else:
            print("KRW 5000 미만")

    elif result["decision"] == "sell":
        my_btc = upbit.get_balance("KRW-BTC")
        sell_amount = my_btc * (result["percentage"] / 100)
        current_price = pyupbit.get_orderbook(ticker="KRW-BTC")["orderbook_units"][0]["ask_price"]
        if sell_amount * current_price > 5000:
            # upbit.sell_market_order("KRW-BTC", sell_amount)    # 실제 거래소에서 매매
            save_trade("sell", result["reason"])
        else:
            print("BTC 5000 미만")

    elif result["decision"] == "hold":
        save_trade("hold", result["reason"])


# 수익률 임계값
MIN_PROFIT_THRESHOLD = -5.0

def stop_auto_trading(profit):

    print(f"수익률이 {MIN_PROFIT_THRESHOLD}% 이하입니다. BTC 전량 매도 및 자동매매 중단.")
    my_btc = upbit.get_balance("KRW-BTC")
    current_price = pyupbit.get_orderbook(ticker="KRW-BTC")["orderbook_units"][0]["ask_price"]
    if my_btc * current_price > 5000:
        # upbit.sell_market_order("KRW-BTC", my_btc)  # 실제 거래소에서 매매
        print("BTC 전량 매도 실행됨.")
        save_trade("forced_sell", f"수익률 {profit:.2f}%로 인해 강제 매도")
    else:
        print("BTC 잔액이 5000원 미만이어서 매도 생략됨.")

    schedule.clear(auto_trading)    # 자동매매 중단
    return


def auto_trading():

    # 현재 수익률 계산
    income, profit = calculate_profit()

    if profit <= MIN_PROFIT_THRESHOLD:
        stop_auto_trading(profit)
    
    # 공포 탐욕 지수
    fear_greed_index = get_fear_and_greed_index()

    # 비트코인 관련 뉴스
    news_data = news()

    # 호가 데이터
    orderbook = pyupbit.get_orderbook("KRW-BTC")

    # 30시간 시간봉 데이터
    df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=30)
    df_hourly = dropna(df_hourly)
        
    # 72분 5분봉 데이터
    df_15minute = pyupbit.get_ohlcv("KRW-BTC", interval="minute15", count=72)
    df_15minute = dropna(df_15minute)

    # 전략별 매매 판단 받기
    agent_outputs = []
    for strategy_path in strategy_paths:
        decision = strategy_agent(strategy_path, df_15minute, df_hourly, orderbook)
        agent_outputs.append({"agent": os.path.basename(strategy_path), **decision})

    # 시장 심리 판단 받기
    sentiment_decision = market_sentiment_agent(news_data, fear_greed_index)
    agent_outputs.append({"agent": "sentiment", **sentiment_decision})

    # 최종 판단
    final_decision = final_decision_agent(agent_outputs)

    print(json.dumps(agent_outputs, indent=2, ensure_ascii=False))
    print(json.dumps(final_decision, indent=2, ensure_ascii=False))

    # 매매 실행
    execute_trade(final_decision)


if __name__ == "__main__":
    auto_trading()

    # 15분마다 자동매매 진행
    """""
    schedule.every(15).minutes.do(auto_trading)

    while True:
        schedule.run_pending()
        time.sleep(1)
        """
    
