import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BOT2_CONFIG = {
    'name': 'Bot 2 - GitHub Actions Live Bot',
    'symbols': {
        'VGI': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': True},
        'STB': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': True},
        'FRT': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': True},
        'ELC': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': False},
        'HDB': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': True},
        'TCB': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
        'PVT': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': False},
        'GEX': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': False},
        'BID': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
        'MWG': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
        'PET': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': True},
        'VIX': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.08, 'ma100': True},
        'HCM': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.05, 'ma100': True},
        'MBB': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
        'BAB': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
        'BMI': {'sl': 3.0, 'tp': 6.0, 'holding': 25, 'pullback': 0.06, 'ma100': False},
    }
}

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Thiếu thông tin Telegram Token hoặc Chat ID trong Secrets.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Lỗi gửi Telegram: {e}")
        return False

def is_market_hours():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(tz_vn)
    if now.weekday() >= 5: return False # Thứ 7, Chủ Nhật nghỉ
    ct = now.time()
    return (datetime.strptime("09:00", "%H:%M").time() <= ct <= datetime.strptime("11:30", "%H:%M").time()) or \
           (datetime.strptime("13:00", "%H:%M").time() <= ct <= datetime.strptime("14:30", "%H:%M").time())

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_alma(series, window=9, offset=0.85, sigma=6.0):
    m = int(offset * (window - 1))
    s = window / sigma
    weights = np.exp(-((np.arange(window) - m) ** 2) / (2 * s ** 2))
    weights /= weights.sum()
    return series.rolling(window).apply(lambda x: np.dot(x, weights), raw=True)

def calculate_indicators(df):
    df = df.copy()
    df['tenkan_1'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun_1'] = (df['high'].rolling(17).max() + df['low'].rolling(17).min()) / 2
    df['senkou_b_2'] = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2
    
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma100'] = df['close'].rolling(100).mean()
    df['alma'] = calculate_alma(df['close'], window=9, offset=0.85, sigma=6.0)
    
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def scan_signals():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    print(f"🔍 [{datetime.now(tz_vn).strftime('%H:%M:%S %d/%m/%Y')}] Bắt đầu quét tín hiệu...")
    
    # Lấy dữ liệu 90 ngày gần nhất để đảm bảo đủ số lượng nến tính chỉ báo
    start_date = (datetime.now(tz_vn) - timedelta(days=90)).strftime('%Y-%m-%d')
    
    for symbol, cfg in BOT2_CONFIG['symbols'].items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_date, interval="1H")
            if df is None or len(df) < 140: continue
            
            df = calculate_indicators(df)
            prev = df.iloc[-2]
            curr = df.iloc[-1]
            
            cross_up = (prev['tenkan_1'] <= prev['kijun_1']) and (curr['tenkan_1'] > curr['kijun_1'])
            dist_kijun = abs(curr['close'] - curr['kijun_1']) / curr['kijun_1']
            pb_ok = dist_kijun <= cfg['pullback']
            
            trend_ok = (curr['close'] > curr['ma20']) and (curr['close'] > curr['alma'])
            rsi_ok = (curr['rsi'] > 40) and (curr['rsi'] < 80)
            vol_ok = curr['volume'] > curr['vol_ma']
            cloud_ok = curr['close'] > curr['senkou_b_2']
            ma100_ok = (curr['close'] > curr['ma100']) if cfg['ma100'] else True
            
            if cross_up and pb_ok and trend_ok and rsi_ok and vol_ok and cloud_ok and ma100_ok and pd.notnull(curr['atr']) and curr['atr'] > 0:
                entry = curr['close']
                sl = entry - (cfg['sl'] * curr['atr'])
                tp = entry + (cfg['tp'] * curr['atr'])
                
                msg = (
                    f"🚀 <b>[{BOT2_CONFIG['name']} - #{symbol}]</b>\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Mua (Entry):</b> {entry:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP {cfg['tp']}x ATR):</b> {tp:,.0f} VND (+{((tp/entry)-1)*100:.1f}%)\n"
                    f"🛡 <b>Cắt lỗ (SL {cfg['sl']}x ATR):</b> {sl:,.0f} VND (-{((1-(sl/entry)))*100:.1f}%)\n"
                    f"⏱ <b>Thời gian giữ:</b> {cfg['holding']} nến H1 (~{cfg['holding']/4:.1f} ngày)\n"
                    f"📉 <b>Pullback Kijun:</b> {dist_kijun*100:.2f}% (Max {cfg['pullback']*100:.0f}%)\n"
                    f"🕒 <b>Thời gian:</b> {curr['time']}"
                )
                print(f"✅ GỬI THÀNH CÔNG TÍN HIỆU: {symbol} giá {entry:,.0f}")
                send_telegram(msg)
        except Exception as e:
            print(f"⚠️ Lỗi xử lý mã {symbol}: {e}")
            continue

if __name__ == "__main__":
    if is_market_hours():
        scan_signals()
    else:
        print("💤 Ngoài khung giờ giao dịch chứng khoán Việt Nam.")
 
