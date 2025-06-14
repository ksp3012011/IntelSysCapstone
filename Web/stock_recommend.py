from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
import os
import requests
import json


load_dotenv()
client = OpenAI()

# 오늘 날짜 및 5년 전 시작일 계산
today = datetime.today()
today_str = today.strftime('%Y%m%d')
start_date = (today - timedelta(days=365*5)).replace(month=1, day=1)
year = today.replace(month=1, day=1)

# 최근 영업일 기준
latest_date = stock.get_nearest_business_day_in_a_week(today_str)

# 시가총액 데이터 수집
cap_df = stock.get_market_cap_by_ticker(latest_date, market='KOSPI')
cap_df['종목명'] = [stock.get_market_ticker_name(code) for code in cap_df.index]
cap_df['종목코드'] = cap_df.index
cap_df.set_index('종목명', inplace=True)
top_10 = cap_df.sort_values(by='시가총액', ascending=False).head(10)

# 뉴스 API 사용
url = 'https://newsapi.org/v2/everything'

def get_news(keyword):
    params = {
        'q': keyword,
        'pageSize': 3,
        'language': 'ko',
        'sortBy': 'publishedAt',
        'apiKey': os.getenv('NEWS_API')
    }
    response = requests.get(url, params=params)
    return response.json()


# 종목별 데이터 수집
analysis_data = []
for name, row in top_10.iterrows():
    code = row['종목코드']
    # 한국거래소로부터 연간 재무 지표 받아오기
    fundamentals = stock.get_market_fundamental(start_date, year, code, freq="y")
    news_json = get_news(name)
    
    news_titles = []
    if news_json.get('status') == 'ok':
        news_titles = [article['title'] for article in news_json.get('articles', [])]
    
    analysis_data.append({
        'name': name,
        'code': code,
        'fundamentals': fundamentals.reset_index().to_dict(orient='records'),
        'news': news_titles
    })

def stock_recommend():

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
                응답은 반드시 JSON 형식으로 작성"""
            },
            {
            "role": "user",
            "content": json.dumps(analysis_data, ensure_ascii=False, default=str)
            }
        ],
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)


result = stock_recommend()
print(json.dumps(result, indent=2, ensure_ascii=False))
