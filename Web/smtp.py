import smtplib
from sql import get_db_connection, fetch_trades_from_db, get_all_emails, fetch_investment_summary, fetch_investment_summary_stock
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 보내는 사람, 받는 사람, 제목, 본문 설정
sender_email = "xxx@gmail.com"
password = "---"  # 앱 비밀번호 사용해야 함 (보통 2단계 인증시 필요)

def send_email(subject, body, to_email):
    msg = MIMEMultipart()

    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)  # TLS 포트
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        print("이메일 전송 완료!")
    except Exception as e:
        print(f"이메일 전송 실패: {e}")
    finally:
        server.quit()


def send_trade(to_email, trade_name, amount, total, trade_type):
    current_time = datetime.now().strftime("%Y년 %m월 %d일")

    subject = f"{trade_type} 거래 알림"
    body =  f"현재 자동매매를 통해 거래가 진행되었습니다.\n\n" \
            f"매매일자: {current_time}\n" \
            f"거래종목: {trade_name} \n" \
            f"수량: {amount} \n" \
            f"체결가: {total}원\n" \
            f"내용: {trade_type}체결\n"

    send_email(subject, body, to_email)

def send_paper():
    current_time = datetime.now().strftime("%Y년 %m월 %d일")

    email_list = get_all_emails()

    for to_email in email_list:
        print(f"Sending email to {to_email}")
        invest = fetch_investment_summary("bitcoin_trading.db")
        invest += fetch_investment_summary_stock("stock_trading.db")

        subject = f"{current_time} 투자 보고서"
        body =  f"{current_time} 투자 보고서를 전달합니다.\n\n" \
                f"총 투자금: {invest['total_inv']}원\n" \
                f"손익: {invest['total_pro']}원\n" \
                f"수익률: {invest['pro_rate']}%\n"

        send_email(subject, body, to_email)