import requests
import json
import os
import re
from dataclasses import dataclass
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv(dotenv_path='api.key') 

@dataclass
class Source:
    id: Optional[str]
    name: str

@dataclass
class Article:
    source: Source
    author: Optional[str]
    title: str
    description: Optional[str]
    url: str
    urlToImage: Optional[str]
    publishedAt: str
    content: Optional[str]

@dataclass
class NewsResponse:
    status: str
    totalResults: int
    articles: List[Article]

# News API 엔드포인트 및 API 키 설정
url = 'https://newsapi.org/v2/everything'

def parse_news_response(data: dict) -> NewsResponse:
    articles = [
        Article(
            source=Source(**a['source']),
            author=a.get('author'),
            title=a['title'],
            description=a.get('description'),
            url=a['url'],
            urlToImage=a.get('urlToImage'),
            publishedAt=a['publishedAt'],
            content=a.get('content')
        ) for a in data.get('articles', [])
    ]
    return NewsResponse(
        status=data['status'],
        totalResults=data['totalResults'],
        articles=articles
    )

def get_news(category):
    # GET 요청 보내기기
    params = {
        'q': category,  # 원하는 뉴스
        'pageSize': 5,
        'language': 'ko',
        'sortBy': 'publishedAt',
        'apiKey': os.getenv('NEWS_API')  # 발급받은 API 키
    }
    response = requests.get(url, params=params)
    data = response.json()
    print(data)  # 응답 데이터 출력
    news_object = parse_news_response(data)

    return news_object