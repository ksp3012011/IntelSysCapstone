from flask import Flask, render_template, request, redirect, url_for, session
from sql import get_db_connection, fetch_trades_from_db, fetch_trades_statistics, display_coin, display_stock
from newsapi import get_news
from smtp import send_email, send_trade, send_paper
import random 
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
from auto_trade import auto_trading
from stock_trade import recommend_stock, auto_stock_trading
import time

app = Flask(__name__)
app.secret_key = '8f21c742f44c4419adf0a9a3f9dce95ebd6ce54e78c3d2b312c8bc08c012ae6d'

# 매매기록 저장된 sqlite 불러오기
db_path = 'bitcoin_trading.db'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM login WHERE email = %s AND password = %s', (email, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                session['user_email'] = user['email']  # 세션에 저장
                return redirect(url_for('investment'))
            else:
                error = '이메일 또는 비밀번호가 잘못되었습니다.'
        except Exception as e:
            error = '서버에 문제가 발생했습니다.'
            print('DB ERROR:', e)

    return render_template('login.html', error=error)

'''@app.route('/news')
def news():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    news_object = get_news('비트코인 NOT 블록체인')

    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    news_article = {}
    for i, article in enumerate(news_object.articles):
        news_article[i] = {
            "title": article.title,
            "description": article.description}
            #"url": article.url}
    return render_template('news.html', date=today, news=news_article[random.randint(0, len(news_article) - 1)])
'''
@app.route('/investment')
def investment():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    investments = get_investments_data()
    return render_template('investment.html', investments=investments)

def get_investments_data():

    #investments = fetch_trades_statistics("bitcoin_trading.db")
    investments = display_coin() + display_stock()

    return investments



@app.route('/settings')
def settings():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    email = session['user_email']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT btc_auto, stock_auto, mail_receive FROM login WHERE email = %s', (email,))
        user_settings = cursor.fetchone()
        cursor.close()
        conn.close()

        btc_auto = user_settings['btc_auto']
        stock_auto = user_settings['stock_auto']
        mail_receive = user_settings['mail_receive']

    except Exception as e:
        print('DB ERROR:', e)
        btc_auto = stock_auto = mail_receive = False  # 실패하면 기본 False

    return render_template('settings.html', btc_auto=btc_auto, stock_auto=stock_auto, mail_receive=mail_receive)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    email = session['user_email']

    btc_auto = 'btc_auto' in request.form
    stock_auto = 'stock_auto' in request.form
    mail_receive = 'mail_receive' in request.form

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # MySQL에서는 True/False 대신 1/0으로 저장
        cursor.execute('''
            UPDATE login 
            SET btc_auto = %s, stock_auto = %s, mail_receive = %s 
            WHERE email = %s
        ''', (int(btc_auto), int(stock_auto), int(mail_receive), email))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print('DB ERROR:', e)

    return redirect(url_for('investment'))


#스케줄러 설정
scheduler_of_paper = BackgroundScheduler()
scheduler_of_paper.add_job(
    func=send_paper,
    trigger='interval',
    seconds=0,
    minutes=0,
    hours=24,
    id='paper_email_job',
    replace_existing=True
)

scheduler_of_coin_trade = BackgroundScheduler()
scheduler_of_coin_trade.add_job(
    func=auto_trading,
    trigger='interval',
    seconds=0,
    minutes=5,
    hours=0,
    id='coin_trading_job',
    replace_existing=True
)


scheduler_of_stock_trade = BackgroundScheduler()
scheduler_of_stock_trade.add_job(
    func=auto_stock_trading,
    trigger='interval',
    seconds=0,
    minutes=3,
    hours=0,
    id='stock_trading_job',
    replace_existing=True
)


if __name__ == '__main__':
    import os

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        scheduler_of_paper.start()
        scheduler_of_coin_trade.start()
        time.sleep(90)

        recommend_stock()
        scheduler_of_stock_trade.start()
    app.run(host='0.0.0.0', port=15000, debug=True)
    
