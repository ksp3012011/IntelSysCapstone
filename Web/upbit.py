import jwt
import uuid
import hashlib
import requests
import time

import os

from dotenv import load_dotenv

load_dotenv(dotenv_path='api.key') 

# Upbit API 키 (보안상 api.key 같은 파일로 분리하는 걸 추천)
ACCESS_KEY = os.getenv('UPBIT_ACCESS_KEY')
SECRET_KEY = os.getenv('UPBIT_SECRET_KEY')
SERVER_URL = 'https://api.upbit.com'

#ipaccess
def get_balance():
    payload = {
        'access_key': ACCESS_KEY,
        'nonce': str(uuid.uuid4()),
    }

    jwt_token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    authorize_token = 'Bearer {}'.format(jwt_token)
    headers = {
        'Authorization': authorize_token,
    }

    res = requests.get(SERVER_URL + '/v1/accounts', headers=headers)
    return res.json()

# 사용 예시
balances = get_balance()
print(balances)  # 응답 데이터를 먼저 확인
for balance in balances:
    print(f"{balance['currency']} : {balance['balance']} (locked: {balance['locked']})")