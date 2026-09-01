import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# 1. CẤU HÌNH BOT TELEGRAM & TOP 10 MÃ CHỌN LỌC TỐI ƯU
# ==============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

WATCHLIST = ['BMI', 'PVT', 'VIX', 'FCN', 'TCB', 'GEX', 'VHM', 'TDM', 'DQC', 'BID']

# ==============================================================================
# 2. HÀM GỬI TELEGRAM & KIỂM TRA GIỜ GIAO DỊCH
# ==============================================================================
def send_telegram(message):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Lỗi gửi Telegram: {e}")
        return False

def is_market_hours():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(tz_vn)
    if now.weekday() >= 5:
        return False
    ct = now.time()
    session1 = datetime.strptime("09:00", "%H:%M").time() <= ct <= datetime.strptime("11:30", "%H:%M").time()
    session2 = datetime.strptime("13:00", "%H:%M").time() <= ct <= datetime.strptime("14:30", "%H:%M").time()
    return session1 or session2

# ==============================================================================
# 3. TÍNH TOÁN CHỈ BÁO KỸ THUẬT H1
# ==============================================================================
def calculate_indicators(df):
    df = df.copy()
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

# ==============================================================================
# 4. HÀM QUÉT TÍN HIỆU REAL-TIME
# ==============================================================================
def scan_signals():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_str = datetime.now(tz_vn).strftime("%H:%M:%S %d/%m/%Y")
    print(f"\n🔍 [{now_str}] Bắt đầu quét Top 10 mã chọn lọc...")
    
    # 1. Kiểm tra xu hướng VN-Index
    vni_ok = False
    for src in ["VCI", "TCBS", "KBS"]:
        try:
            quote = Quote(symbol="VNINDEX", source=src)
            df_vni = quote.history(start="2026-01-01", interval="1H")
            if df_vni is not None and not df_vni.empty:
                df_vni['MA20'] = df_vni['close'].rolling(20).mean()
                last_vni = df_vni.iloc[-1]
                vni_ok = last_vni['close'] > last_vni['MA20']
                print(f"📊 VN-Index ({last_vni['close']:.2f}) {'TRÊN' if vni_ok else 'DƯỚI'} MA20 H1")
                break
        except:
            continue
            
    if not vni_ok:
        print("⚠️ VN-Index chưa đạt điều kiện (VNI < MA20). Bỏ qua lượt quét.")
        return

    # 2. Quét Top 10 mã
    for symbol in WATCHLIST:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start="2026-01-01", interval="1H")
            if df is None or len(df) < 30:
                continue
                
            df = calculate_indicators(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Điều kiện Tenkan cắt lên Kijun
            cross_up = (prev['tenkan'] <= prev['kijun']) and (curr['tenkan'] > curr['kijun'])
            
            if cross_up and pd.notnull(curr['atr']) and curr['atr'] > 0:
                entry = curr['close']
                sl = entry - (2.0 * curr['atr'])
                tp = entry + (4.5 * curr['atr'])
                
                msg = (
                    f"🚀 <b>[TÍN HIỆU MUA TOP 10 - #{symbol}]</b>\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Mua (Entry):</b> {entry:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP 4.5x ATR):</b> {tp:,.0f} VND (+{((tp/entry)-1)*100:.1f}%)\n"
                    f"🛡 <b>Cắt lỗ ban đầu (SL 2.0x ATR):</b> {sl:,.0f} VND (-{((1-(sl/entry)))*100:.1f}%)\n"
                    f"💡 <b>Lưu ý Trailing Stop:</b> Khi lãi >= 2x ATR, dời SL lên (Giá - 1.5x ATR)\n"
                    f"📈 <b>Tỷ trọng Vốn:</b> Tăng +50% quy mô nếu lệnh trước của mã này thắng\n"
                    f"🕒 <b>Thời gian:</b> {curr['time']}"
                )
                
                print(f"✅ TÍN HIỆU MỚI: {symbol} giá {entry:,.0f}")
                send_telegram(msg)
                
        except Exception as e:
            continue

# ==============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH (CHẠY 1 LẦN CHO GITHUB ACTIONS)
# ==============================================================================
if __name__ == "__main__":
    if is_market_hours():
        print("⏰ Đang trong khung giờ giao dịch -> Bắt đầu quét...")
        scan_signals()
    else:
        print("💤 Ngoài khung giờ giao dịch. Bỏ qua lượt quét.")
