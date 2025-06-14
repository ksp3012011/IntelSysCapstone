import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
import numpy as np
import pyupbit
import ta
from ta.utils import dropna
import pandas as pd
from datetime import datetime


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
    "strategy2.txt": ["bollinger_bands"],           # 볼린저 밴드 스퀴즈 전략1
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

# 투자 전략별 필요 기술적 지표 계산
def calculate_indicators(df, best_match):
    file_name = get_strategy_filename(best_match)
    indicators = strategy_indicators.get(file_name, [])

    # 기본값: 원본 OHLCV
    use_heikin_ashi = "stockastic_rsi" in indicators
    working_df = heikin_ashi(df) if use_heikin_ashi else df.copy()

    # OHLCV 컬럼만 복사
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

def main():
    best_match1 = strategy_paths[0]
    best_match2 = strategy_paths[1]
    best_match3 = strategy_paths[2]  # 예: strategy3.txt 선택 (인덱스 조정 가능)

    # OHLCV 데이터 가져오기
    df = pyupbit.get_ohlcv("KRW-BTC", interval="minute30", count=72)
    processed_df1 = calculate_indicators(df, best_match1)
    processed_df2 = calculate_indicators(df, best_match2)
    processed_df3 = calculate_indicators(df, best_match3)


    file_name1 = get_strategy_filename(best_match1)
    file_name2 = get_strategy_filename(best_match2)
    file_name3 = get_strategy_filename(best_match3)
    print(f"=== 전략: {file_name1} ===")
    print(processed_df1.tail(10))
    print(f"=== 전략: {file_name2} ===")
    print(processed_df2.tail(10))
    print(f"=== 전략: {file_name3} ===")
    print(processed_df3.tail(10))

if __name__ == "__main__":
    main()
