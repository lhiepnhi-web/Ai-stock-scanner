import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# 1. CẤU HÌNH BOT TELEGRAM & DANH MỤC WATCHLIST
# ==============================================================================
# Ưu tiên lấy từ GitHub Secrets, nếu không có sẽ lấy chuỗi mặc định
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

WATCHLIST = [
    'VIX', 'PNJ', 'DGW', 'PVT', 'DQC', 'LCG', 'DIG', 'TCB', 'YEG', 'BID', 
    'TPB', 'TDM', 'FCN', 'TV2', 'VSC', 'VRE', 'MBB', 'PET', 'TMP', 'CTG', 
    'HDB', 'IJC', 'SAB', 'PC1', 'SSI', 'BFC', 'HSG', 'BMI', 'CTD', 'DPR', 
    'VNM', 'VCG', 'NLG', 'GMD', 'GEX', 'PLX', 'CII', 'CTS', 'AAA', 'VPB', 
    'VHM', 'NTP', 'SZC', 'HCM', 'PDR', 'FTS', 'DGC', 'MBS'
]
WATCHLIST = list(dict.fromkeys(WATCHLIST))

# ==============================================================================
# 2. HÀM TƯƠNG TÁC TELEGRAM
# ==============================================================================
def send_telegram(message):
    """Hàm gửi tin nhắn qua Telegram Bot API"""
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("⚠️ Chưa cấu hình TELEGRAM_BOT_TOKEN!")
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

# ==============================================================================
# 3. HÀM KIỂM TRA GIỜ GIAO DỊCH VÀ TÍNH TOÁN KỸ THUẬT
# ==============================================================================
def is_market_hours():
    """Kiểm tra thời gian hiện tại có thuộc khung giờ giao dịch chứng khoán VN"""
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(tz_vn)
    
    # Thứ 7 (5) và Chủ Nhật (6) nghỉ
    if now.weekday() >= 5:
        return False
        
    current_time = now.time()
    session1 = datetime.strptime("09:00", "%H:%M").time() <= current_time <= datetime.strptime("11:30", "%H:%M").time()
    session2 = datetime.strptime("13:00", "%H:%M").time() <= current_time <= datetime.strptime("14:30", "%H:%M").time()
    
    return session1 or session2

def calculate_indicators(df):
    """Tính Tenkan, Kijun và ATR(14) trên khung H1"""
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

# ==============================================================================
# 4. HÀM QUÉT TÍN HIỆU THỰC CHIẾN
# ==============================================================================
def scan_signals():
    """Quét dữ liệu real-time và phát hiện tín hiệu mua"""
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_str = datetime.now(tz_vn).strftime("%H:%M:%S %d/%m/%Y")
    print(f"\n🔍 [{now_str}] Bắt đầu quét tín hiệu thị trường...")
    
    # 1. Lấy xu hướng VN-Index (VNI > MA20 H1)
    vni_ok = False
    for src in ["VCI", "TCBS", "KBS"]:
        try:
            quote = Quote(symbol="VNINDEX", source=src)
            df_vni = quote.history(start="2026-01-01", interval="1H")
            if df_vni is not None and not df_vni.empty:
                df_vni['MA20'] = df_vni['close'].rolling(20).mean()
                last_vni = df_vni.iloc[-1]
                vni_ok = last_vni['close'] > last_vni['MA20']
                print(f"📊 VN-Index ({last_vni['close']:.2f}) {'nằm TRÊN' if vni_ok else 'nằm DƯỚI'} MA20 H1")
                break
        except:
            continue
            
    if not vni_ok:
        print("⚠️ Xu hướng VN-Index chưa đạt điều kiện (VNI < MA20). Bỏ qua lượt quét.")
        return

    signals_found = 0
    # 2. Lặp qua danh mục cổ phiếu
    for symbol in WATCHLIST:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start="2026-01-01", interval="1H")
            
            if df is None or len(df) < 30:
                continue
                
            df = calculate_indicators(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Điều kiện Cắt lên Tenkan / Kijun
            cross_up = (prev['tenkan'] <= prev['kijun']) and (curr['tenkan'] > curr['kijun'])
            
            if cross_up and pd.notnull(curr['atr']) and curr['atr'] > 0:
                entry_price = curr['close']
                sl_price = entry_price - (2.0 * curr['atr'])
                tp_price = entry_price + (4.5 * curr['atr'])
                
                msg = (
                    f"🚨 <b>[TÍN HIỆU MUA - ICHIMOKU H1]</b> 🚨\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Mua (Entry):</b> {entry_price:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP 4.5x ATR):</b> {tp_price:,.0f} VND (+{((tp_price/entry_price)-1)*100:.1f}%)\n"
                    f"🛡 <b>Cắt lỗ (SL 2.0x ATR):</b> {sl_price:,.0f} VND (-{((1-(sl_price/entry_price)))*100:.1f}%)\n"
                    f"⏱ <b>Thời gian giữ:</b> T+2.5 (Tối thiểu 12 nến H1)\n"
                    f"🕒 <b>Nến phát hiện:</b> {curr['time']}"
                )
                
                print(f"✅ TÍN HIỆU MỚI: {symbol} giá {entry_price:,.0f}")
                send_telegram(msg)
                signals_found += 1
                
        except Exception as e:
            continue
            
    if signals_found == 0:
        print("ℹ️ Không tìm thấy tín hiệu mua mới trong lượt quét này.")

# ==============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH (CHẠY 1 LẦN DÀNH CHO GITHUB ACTIONS)
# ==============================================================================
if __name__ == "__main__":
    if is_market_hours():
        print("⏰ Đang trong khung giờ giao dịch -> Bắt đầu quét...")
        scan_signals()
    else:
        print("💤 Ngoài khung giờ giao dịch. Bỏ qua lượt quét này.")
 
