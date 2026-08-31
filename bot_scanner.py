# ============================================
# BOT QUÉT TÍN HIỆU THỰC CHIẾN & BÁO TELEGRAM
# ============================================

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# Lấy cấu hình Telegram từ GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Thiếu cấu hình Telegram!")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📤 Đã gửi tín hiệu về Telegram!")
    except Exception as e:
        print(f"❌ Lỗi gửi Telegram: {e}")

# Danh sách mã theo dõi thực chiến (37 mã dương)
WATCHLIST = [
    'VIX', 'PNJ', 'DGW', 'BID', 'BVH', 'APS', 'SZC', 'NVB',
    'MBB', 'PVT', 'SSI', 'GEX', 'HT1', 'DGC', 'DIG', 'HSG', 'VGC', 'FCN', 'VCI', 'SAB',
    'IJC', 'DXG', 'CTG', 'L14', 'PDR', 'TPB', 'BMI', 'GMD', 'ANV', 'CSM', 'DHG', 'POW', 'NTP', 'PLX', 'NLG', 'VRE', 'VCG'
]

# Cấu hình chiến lược
CONFIG = {
    "min_adx": 15,
    "max_rsi": 75,
    "min_volume_factor": 0.8,
}

def calculate_indicators(df):
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # Tính ADX đơn giản
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = np.abs(df['high'] - df['close'].shift())
    df['low_close'] = np.abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_hist'] = (df['ema12'] - df['ema26']) - (df['ema12'] - df['ema26']).ewm(span=9, adjust=False).mean()
    
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']
    return df

def check_market():
    # Lấy dữ liệu VN-Index mới nhất
    for src in ["VCI", "TCBS", "KBS"]:
        try:
            quote = Quote(symbol="VNINDEX", source=src)
            # Lấy dữ liệu 30 ngày gần nhất
            df_vni = quote.history(start=(datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d'), 
                                   end=datetime.now().strftime('%Y-%m-%d'), interval="1H")
            if df_vni is not None and not df_vni.empty:
                df_vni['VNI_MA20'] = df_vni['close'].rolling(20).mean()
                df_vni['VNI_Vol_MA20'] = df_vni['volume'].rolling(20).mean()
                latest = df_vni.iloc[-1]
                vni_ok = latest['close'] > latest['VNI_MA20']
                liq_ok = latest['volume'] >= 0.7 * latest['VNI_Vol_MA20']
                return vni_ok, liq_ok
        except:
            continue
    return True, True # Mặc định cho qua nếu lỗi kết nối vni

def run_realtime_scanner():
    print("🔍 Bắt đầu quét tín hiệu thực chiến...")
    vni_ok, liq_ok = check_market()
    
    if not vni_ok:
        print("⚠️ Thị trường chung (VN-Index) đang xấu hơn MA20. Tạm dừng quét mua.")
        return

    signals = []
    
    for symbol in WATCHLIST:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=(datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d'), 
                               end=datetime.now().strftime('%Y-%m-%d'), interval="1H")
            
            if df is None or df.empty or len(df) < 30:
                continue
                
            df = calculate_indicators(df)
            
            # Lấy nến hiện tại (hoặc nến vừa đóng cửa gần nhất) và nến trước đó
            row = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Điều kiện giao cắt Ichimoku (Tenkan cắt lên Kijun)
            cross_up = (prev['tenkan'] <= prev['kijun']) and (row['tenkan'] > row['kijun'])
            
            volume_ok = row['volume_ratio'] > CONFIG['min_volume_factor']
            macd_ok = row['macd_hist'] > 0
            
            if cross_up and volume_ok and macd_ok:
                signals.append({
                    'symbol': symbol,
                    'price': row['close'],
                    'time': row['time']
                })
            time.sleep(2)
        except Exception as e:
            print(f"Lỗi mã {symbol}: {e}")
            continue

    # Tổng hợp và bắn tin nhắn nếu có mã đạt điều kiện Mua
    if signals:
        msg = "🚨 *PHÁT HIỆN TÍN HIỆU MUA (REAL-TIME)* 🚨\n\n"
        for sig in signals:
            msg += f"🟢 Mã: *{sig['symbol']}*\n"
            msg += f"• Giá hiện tại: `{sig['price']:,.1f}`\n"
            msg += f"• Thời gian: `{sig['time']}`\n\n"
        send_telegram_message(msg)
    else:
        print("ℹ️ Không có mã nào phát sinh tín hiệu mới trong kỳ quét này.")

if __name__ == "__main__":
    run_realtime_scanner()
 
