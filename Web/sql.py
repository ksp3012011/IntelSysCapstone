import mysql.connector
import sqlite3

# MySQL 연결 설정
def get_db_connection():
    return mysql.connector.connect(
        host='--',
        port=3306,
        user='--',
        password='--',
        database='agent_login'
    )


def get_all_emails():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT email FROM login WHERE mail_receive = 1;')
        results = cursor.fetchall()

        # [("a@a.com",), ("b@b.com",)] 형태
        email_list = [row[0] for row in results]

        cursor.close()
        conn.close()

        return email_list

    except Exception as e:
        print('DB ERROR:', e)
        return []
    
def get_user_settings(email):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT btc_auto, stock_auto, mail_receive FROM login WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            return {
                'btc_auto': user[0] == 1,
                'stock_auto': user[1] == 1,
                'mail_receive': user[2] == 1
            }
        else:
            return None  # 사용자가 없을 경우

    except mysql.connector.Error as err:
        print("DB Error:", err)
        return None

'''
0|id|INTEGER|0||1
1|strategy|TEXT|0||0
2|timestamp|TEXT|0||0
3|decision|TEXT|0||0
4|reason|TEXT|0||0
5|btc_balance|REAL|0||0
6|krw_balance|REAL|0||0
'''
#SQLite 연결 설정
def fetch_trades_from_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        
        # 결과를 딕셔너리 형태로 사용 가능하게 설정
        conn.row_factory = sqlite3.Row  
        cursor = conn.cursor()

        cursor.execute("SELECT timestamp, btc_balance, krw_balance FROM trades ORDER BY timestamp DESC;")
        rows = cursor.fetchall()

        # 딕셔너리 리스트로 변환
        results = []
        for row in rows:
            results.append({
                "time": row["timestamp"], 
                "profit": f"{row['krw_balance']:.2f}원",
                "value": f"{(row['btc_balance']):.1f} BTC", 
            })

        return results

    except sqlite3.Error as e:
        print("DB 오류 발생:", e)
        return []

    finally:
        if conn:
            conn.close()

def fetch_trades_statistics(db_path):
    try:
        conn = sqlite3.connect(db_path)
        
        # 결과를 딕셔너리 형태로 사용 가능하게 설정
        conn.row_factory = sqlite3.Row  
        cursor = conn.cursor()

        cursor.execute("""SELECT symbol, 
                       SUM(CASE WHEN decision = 'buy' THEN btc_balance ELSE 0 END) AS total_btc_bought, 
                       SUM(CASE WHEN decision = 'buy' THEN btc_balance * btc_krw_price ELSE 0 END) AS total_spent, 
                       SUM(CASE WHEN decision = 'buy' THEN btc_balance * btc_krw_price ELSE 0 END) AS total_investment,
                       SUM(avg_buy_price) AS total_profit
                       FROM trades 
                       GROUP BY symbol;""")
        rows = cursor.fetchall()

        # 딕셔너리 형태로 변환
        result = []
        for row in rows:
            profit_rate = ((row['total_investment'] + row['total_profit'])-row['total_investment']) / row['total_investment'] * 100 if row['total_investment'] else 0

            result.append({
                "name": row["symbol"],
                "amount": f"{row['total_btc_bought']:.8f}",
                "price": f"{row['total_spent']:.2f}" if row['total_spent'] else "0",
                "change": (f"{profit_rate:.2f}%") + (f"({profit_rate/(float)(100) * row['total_spent']:.2f}원)"),
                #"total_profit": f"{row['total_profit']:.2f}원" if row['total_profit'] else "0원"
            })

        return result
    

    except sqlite3.Error as e:
        print("DB 오류 발생:", e)
        return {}

    finally:
        if conn:
            conn.close()

def display_coin():
    try:
        conn = sqlite3.connect("bitcoin_trading.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 각 코인별 가장 최신(마지막) 거래 기록을 가져오는 SQL 쿼리
        # 이 쿼리는 현재 보유하고 있는 코인의 마지막 상태(잔고, 평단가)를 가져옵니다.
        sql_query = """
        SELECT
            t.symbol,
            t.timestamp,
            t.decision,
            t.btc_balance,
            t.krw_balance,
            t.btc_krw_price,
            t.avg_buy_price
        FROM
            trades t
        JOIN
            (SELECT symbol, MAX(timestamp) AS max_time FROM trades GROUP BY symbol) AS latest
        ON
            t.symbol = latest.symbol AND t.timestamp = latest.max_time;
        """

        cursor.execute(sql_query)
        rows = cursor.fetchall()

        # 딕셔너리 형태로 변환
        result = []
        for row in rows:
            print(row["symbol"], row["timestamp"])

            #current_price = (row['btc_krw_price'] * row['btc_balance'])
            #if current_price == 0:
            #    percent_change = 0
            #else:
            #    percent_change = ((current_price + row['income']) / current_price) - 1
            #result.append({
            #    "name": row["symbol"],
            #    "amount": f"{row['btc_balance']:.8f}",
            #    "price": f"{current_price:.2f}",
            #    "change": f"{percent_change:.2f}%({row['income']:.2f}원)"
            #})

            # 개당 현재 코인 가격 (현재 시세)
            current_coin_price = float(row['btc_krw_price']) if row['btc_krw_price'] is not None else 0.0
            
            # 코인 보유량 (현재 잔고)
            coin_balance = float(row['btc_balance']) if row['btc_balance'] is not None else 0.0
            
            # 개당 코인 평균 매입 단가 (평단가)
            avg_buy_price_per_coin = float(row['avg_buy_price']) if row['avg_buy_price'] is not None else 0.0
            
            # 총 코인 매입가 (현재 보유량 기준의 총 매입 원가)
            # 이 변수명은 '총 매입 평단가' 또는 '총 매수 원가'로 이해하는 것이 정확합니다.
            total_acquisition_cost = coin_balance * avg_buy_price_per_coin
            
            # 총 코인 평가액 (현재 시세 기준의 총 가치)
            total_current_value = coin_balance * current_coin_price
            
            # 손익금 계산
            # 코인을 보유하고 있을 때만 손익을 계산 (보유량이 0이면 손익도 0)
            profit_loss = total_current_value - total_acquisition_cost
            
            # 수익률 계산
            # 매입 원가가 0이 아니고, 코인을 보유하고 있을 때만 수익률을 계산합니다.
            if total_acquisition_cost != 0 and coin_balance > 0:
                profit_rate = profit_loss * 100 / total_acquisition_cost
            else:
                profit_rate = 0.0 # 코인을 보유하지 않거나 매입 원가가 0인 경우 수익률은 0
            
            result.append({
                "name": row["symbol"],
                "amount": f"{coin_balance:.8f}",
                "price": f"{total_acquisition_cost:,.2f}",
                "change": f"{profit_rate:.2f}%({profit_loss:,.2f}원)",
            })

        return result

    except sqlite3.Error as e:
        print("DB 오류 발생:", e)
        return []

    finally:
        if conn:
            conn.close()

def display_stock():
    try:
        conn = sqlite3.connect("stock_trading.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql_query = """
        SELECT
            t.symbol,
            t.timestamp,
            t.decision,
            t.hold_quantity,         -- 보유 주식 수량
            t.remaining_cash,   -- 예수금
            t.current_value,    -- 개당 현재 주식 가격 (DB 컬럼명 'current_value'를 개당 가격으로 간주)
            t.purchase_amount     -- 개당 평균 매입 단가
        FROM
            trades t
        JOIN
            (SELECT symbol, MAX(timestamp) AS max_time FROM trades GROUP BY symbol) AS latest
        ON
            t.symbol = latest.symbol AND t.timestamp = latest.max_time;
        """

        cursor.execute(sql_query)
        rows = cursor.fetchall()

        # 딕셔너리 형태로 변환
        result = []
        for row in rows:
            print(row["symbol"], row["timestamp"])

            #current_price = (row['current_value'])
            #percent_change = row['profit_rate']
            #result.append({
            #    "name": row["symbol"],
            #    "amount": f"{row['quantity']:.0f}",
            #    "price": f"{current_price:.0f}",
            #    "change": f"{row['profit_rate']:.2f}%({row['income']:.0f}원)"
            #})

            # 개당 현재 주식 가격 (DB의 'current_value' 컬럼을 개당 시세로 사용)
            # None 체크 후 float으로 변환
            current_stock_price = float(row['current_value']) if row['current_value'] is not None else 0.0
            
            # 주식 보유량 (현재 잔고)
            stock_balance = float(row['hold_quantity']) if row['hold_quantity'] is not None else 0.0
            
            # 개당 주식 평균 매입 단가 (평단가)
            avg_buy_price = float(row['purchase_amount']) if row['purchase_amount'] is not None else 0.0
            
            # 총 매입가 (현재 보유량 기준의 총 매입 원가)
            total_acquisition_cost = avg_buy_price
            
            # 총 평가액 (현재 시세 기준의 총 가치)
            total_current_value = current_stock_price
            
            # 손익금 계산
            # 주식을 보유하고 있을 때만 손익을 계산 (보유량이 0이면 손익도 0)
            profit_loss_amount = total_current_value - total_acquisition_cost
            
            # 수익률 계산
            # 매입 원가가 0이 아니고, 주식을 보유하고 있을 때만 수익률을 계산합니다.
            if total_acquisition_cost != 0 and stock_balance > 0:
                profit_rate = profit_loss_amount * 100 / total_acquisition_cost
            else:
                profit_rate = 0.0 # 주식을 보유하지 않거나 매입 원가가 0인 경우 수익률은 0

            result.append({
                "name": row["symbol"],
                "amount": f"{stock_balance:,}",
                "price": f"{total_acquisition_cost:,}",
                "change": f"{profit_rate:,.2f}%({profit_loss_amount:,}원)",
            })

        return result

    except sqlite3.Error as e:
        print("DB 오류 발생:", e)
        return []

    finally:
        if conn:
            conn.close()

def fetch_investment_summary(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                SUM(CASE WHEN decision = 'buy' THEN btc_balance * btc_krw_price ELSE 0 END) AS total_investment,
                SUM(income) AS total_profit
            FROM trades;
        """)
        row = cursor.fetchone()

        profit_rate = ((row['total_investment'] + row['total_profit'])-row['total_investment']) / row['total_investment'] * 100 if row['total_investment'] else 0

        summary = {
            "total_inv": f"{row['total_investment']:.2f}" if row['total_investment'] else "0",
            "total_pro": f"{row['total_profit']:.2f}" if row['total_profit'] else "0",
            "pro_rate": f"{(float)(profit_rate):.2f}"
        }

        return summary

    except Exception as e:
        print("DB Error:", e)
        return None
    
def fetch_investment_summary_stock(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                SUM(CASE WHEN decision = 'buy' THEN btc_balance * btc_krw_price ELSE 0 END) AS total_investment,
                SUM(income) AS total_profit
            FROM trades;
        """)
        row = cursor.fetchone()

        profit_rate = ((row['total_investment'] + row['total_profit'])-row['total_investment']) / row['total_investment'] * 100 if row['total_investment'] else 0

        summary = {
            "total_inv": f"{row['total_investment']:.2f}" if row['total_investment'] else "0",
            "total_pro": f"{row['total_profit']:.2f}" if row['total_profit'] else "0",
            "pro_rate": f"{(float)(profit_rate):.2f}"
        }

        return summary

    except Exception as e:
        print("DB Error:", e)
        return None
