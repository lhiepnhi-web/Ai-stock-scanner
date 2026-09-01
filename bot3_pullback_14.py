import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

BOT3_CONFIG = {
    'name': 'Bot 3 - 14 Mã Pullback',
    'symbols': {
        'BVH': {'sl': 4.0, 'tp': 8.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'DGC': {'sl': 4.0, 'tp': 8.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'PLX': {'sl': 4.0, 'tp': 8.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'POW': {'sl': 4.0, 'tp': 8.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'GMD': {'sl': 3.0, 'tp': 6.0, 'holding': 20, 'pullback': 0.03, 'ma100': True},
        'ANV': {'sl': 4.5, 'tp': 9.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'VNM': {'sl': 4.0, 'tp': 8.0, 'holding': 20, 'pullback': 0.04, 'ma100': False},
        'DXG': {'sl': 3.5, 'tp': 7.0, 'holding': 20, 'pullback': 0.03, 'ma100': False},
        'SAB': {'sl': 3.5, 'tp': 7.0, 'holding': 20, 'pullback': 0.02, 'ma100': False},
        'SSI': {'sl': 3.5, 'tp': 7.0, 'holding': 20, 'pullback': 0.02, 'ma100': False},
        'VRE': {'sl': 2.5, 'tp': 5.0, 'holding': 12, 'pullback': 0.02, 'ma100': True},
        'DHG': {'sl': 2.5, 'tp': 5.0, 'holding': 12, 'pullback': 0.02, 'ma100': True},
        'DBD': {'sl': 2.5, 'tp': 5.0, 'holding': 12, 'pullback': 0.02, 'ma100': False},
        'PVI': {'sl': 2.0, 'tp': 4.5, 'holding': 12, 'pullback': 0.02, 'ma100': False},
    }
}

def send_telegram(message):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
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
    if now.weekday() >= 5: return False
    ct = now.time()
    return (datetime.strptime("09:00", "%H:%M").time() <= ct <= datetime.strptime("11:30", "%H:%M").time()) or \
           (datetime.strptime("13:00", "%H:%M").time() <= ct <= datetime.strptime("14:30", "%H:%M").time())

def calculate_indicators(df):
    df = df.copy()
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    df['ma100'] = df['close'].rolling(100).mean()
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def scan_signals():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    print(f"\n🔍 [{datetime.now(tz_vn).strftime('%H:%M:%S %d/%m/%Y')}] Quét {BOT3_CONFIG['name']}...")
    
    for symbol, cfg in BOT3_CONFIG['symbols'].items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start="2026-01-01", interval="1H")
            if df is None or len(df) < 110: continue
            
            df = calculate_indicators(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            cross_up = (prev['tenkan'] <= prev['kijun']) and (curr['tenkan'] > curr['kijun'])
            dist_kijun = abs(curr['close'] - curr['kijun']) / curr['kijun']
            pb_ok = dist_kijun <= cfg['pullback']
            ma_ok = (curr['close'] > curr['ma100']) if cfg['ma100'] else True
            
            if cross_up and pb_ok and ma_ok and pd.notnull(curr['atr']) and curr['atr'] > 0:
                entry = curr['close']
                sl = entry - (cfg['sl'] * curr['atr'])
                tp = entry + (cfg['tp'] * curr['atr'])
                
                msg = (
                    f"⚡ <b>[{BOT3_CONFIG['name']} - #{symbol}]</b>\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Mua (Entry):</b> {entry:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP {cfg['tp']}x ATR):</b> {tp:,.0f} VND (+{((tp/entry)-1)*100:.1f}%)\n"
                    f"🛡 <b>Cắt lỗ (SL {cfg['sl']}x ATR):</b> {sl:,.0f} VND (-{((1-(sl/entry)))*100:.1f}%)\n"
                    f"⏱ <b>Thời gian giữ:</b> {cfg['holding']} nến H1 (~{cfg['holding']/4:.1f} ngày)\n"
                    f"📉 <b>Pullback Kijun:</b> {dist_kijun*100:.2f}% (Max {cfg['pullback']*100:.0f}%)\n"
                    f"🕒 <b>Thời gian:</b> {curr['time']}"
                )
                print(f"✅ TÍN HIỆU BẮN TELEGRAM: {symbol} giá {entry:,.0f}")
                send_telegram(msg)
        except Exception as e:
            continue

if __name__ == "__main__":
    if is_market_hours(): scan_signals()
    else: print("💤 Ngoài khung giờ giao dịch.")
 
