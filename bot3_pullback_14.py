"""
===============================================================================================
BOT 6.5: MEAN REVERSION ULTIMATE - LIVE PRODUCTION & TELEGRAM NOTIFIER
===============================================================================================
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# CẤU HÌNH TELEGRAM & BOT 6.5
# ==============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BOT65_CONFIG = {
    'name': 'Bot 6.5 Mean Reversion Ultimate (Live)',
    'symbols': {
        'STB': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'FPT': {'sl': 1.7, 'tp': 5.0, 'holding': 15},
        'MWG': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'GMD': {'sl': 2.2, 'tp': 5.0, 'holding': 15},
        'DGC': {'sl': 2.7, 'tp': 6.5, 'holding': 20},
        'SSI': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'GAS': {'sl': 2.7, 'tp': 6.0, 'holding': 15},
        'KBC': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
    }
}

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Thiếu thông tin Telegram Token hoặc Chat ID trong GitHub Secrets.")
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
    if now.weekday() >= 5: return False # Nghỉ Thứ 7, Chủ Nhật
    ct = now.time()
    return (datetime.strptime("09:00", "%H:%M").time() <= ct <= datetime.strptime("11:30", "%H:%M").time()) or \
           (datetime.strptime("13:00", "%H:%M").time() <= ct <= datetime.strptime("14:30", "%H:%M").time())

def calculate_indicators(df):
    df = df.copy()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['low_20'] = df['low'].shift(1).rolling(20).min()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def scan_live_signals():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    print(f"🔍 [{datetime.now(tz_vn).strftime('%H:%M:%S %d/%m/%Y')}] Bắt đầu quét tín hiệu Bot 6.5...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90) # Lấy dữ liệu 90 ngày đủ tính chỉ báo
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    for symbol, cfg in BOT65_CONFIG['symbols'].items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_str, end=end_str, interval="1D")
            if df is None or len(df) < 50: 
                continue
            
            df = calculate_indicators(df)
            curr = df.iloc[-1] # Lấy nến giao dịch mới nhất
            
            oversold_rsi = curr['rsi'] < 33
            touch_low = curr['low'] <= curr['low_20'] * 1.02
            
            if oversold_rsi and touch_low and pd.notnull(curr['atr']) and curr['atr'] > 0:
                entry_price = curr['close']
                sl_price = entry_price * (1.0 - cfg['sl'] / 100.0)
                tp_price = entry_price * (1.0 + cfg['tp'] / 100.0)
                
                msg = (
                    f"🚀 <b>[{BOT65_CONFIG['name']} - #{symbol}]</b>\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Đề Xuất (Close):</b> {entry_price:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP +{cfg['tp']}%):</b> {tp_price:,.0f} VND\n"
                    f"🛡 <b>Cắt lỗ (SL -{cfg['sl']}%):</b> {sl_price:,.0f} VND\n"
                    f"📊 <b>RSI(14):</b> {curr['rsi']:.1f} (Ngưỡng < 33)\n"
                    f"⏱ <b>Thời gian giữ tối đa:</b> {cfg['holding']} phiên\n"
                    f"🕒 <b>Thời gian:</b> {curr['time'] if 'time' in curr else 'Hôm nay'}"
                )
                print(f"✅ PHÁT HIỆN TÍN HIỆU: {symbol} - Đã gửi Telegram.")
                send_telegram(msg)
            else:
                print(f"ℹ️ Mã {symbol}: Chưa thỏa mãn điều kiện mua.")
                
        except Exception as e:
            print(f"⚠️ Lỗi xử lý mã {symbol}: {e}")
            continue

if __name__ == "__main__":
    if is_market_hours():
        scan_live_signals()
    else:
        print("💤 Ngoài khung giờ giao dịch chứng khoán Việt Nam.")
 
