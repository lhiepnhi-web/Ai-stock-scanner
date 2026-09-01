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
# 1. CẤU HÌNH BOT TELEGRAM & DANH MỤC 25 MÃ TỐI ƯU (ĐÃ BỎ VTP TỰ ĐỘNG)
# ==============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

OPTIMAL_25 = {
    # Ngân hàng, Bán lẻ, Công nghệ & Mã tốt trước đó (Không chứa VTP & MSR)
    'STB': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'HDB': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'TCB': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'MBB': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'BID': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'VCB': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'BAB': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'PNJ': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'MWG': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'PET': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'FRT': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'DGW': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'HAX': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'TCM': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'FPT': {'sl': 3.5, 'tp': 7.0, 'holding': 20},
    'VGI': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'ELC': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'BMI': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'PVT': {'sl': 2.5, 'tp': 5.0, 'holding': 12},
    'VIX': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'FCN': {'sl': 2.0, 'tp': 4.5, 'holding': 12},
    'GEX': {'sl': 3.0, 'tp': 5.5, 'holding': 16},
    'VHM': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'TDM': {'sl': 3.0, 'tp': 6.0, 'holding': 20},
    'DQC': {'sl': 3.0, 'tp': 6.0, 'holding': 20}
}

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
# 4. QUÉT TÍN HIỆU REAL-TIME THEO CẤU HÌNH TỪNG MÃ
# ==============================================================================
def scan_signals():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_str = datetime.now(tz_vn).strftime("%H:%M:%S %d/%m/%Y")
    print(f"\n🔍 [{now_str}] Bắt đầu quét danh mục 25 mã tối ưu...")
    
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

    # 2. Quét danh mục 25 mã
    for symbol, cfg in OPTIMAL_25.items():
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
                sl = entry - (cfg['sl'] * curr['atr'])
                tp = entry + (cfg['tp'] * curr['atr'])
                holding_days = cfg['holding'] / 4.0
                
                msg = (
                    f"🚀 <b>[TÍN HIỆU MUA DANH MỤC 25 - #{symbol}]</b>\n\n"
                    f"📌 <b>Mã CP:</b> #{symbol}\n"
                    f"💵 <b>Giá Mua (Entry):</b> {entry:,.0f} VND\n"
                    f"🎯 <b>Chốt lời (TP {cfg['tp']}x ATR):</b> {tp:,.0f} VND (+{((tp/entry)-1)*100:.1f}%)\n"
                    f"🛡 <b>Cắt lỗ (SL {cfg['sl']}x ATR):</b> {sl:,.0f} VND (-{((1-(sl/entry)))*100:.1f}%)\n"
                    f"⏱ <b>Thời gian giữ dự kiến:</b> {cfg['holding']} nến H1 (~{holding_days:.1f} ngày)\n"
                    f"📈 <b>Quy tắc vốn:</b> +50% quy mô nếu lệnh trước thắng (Max 15%)\n"
                    f"🕒 <b>Thời gian:</b> {curr['time']}"
                )
                
                print(f"✅ TÍN HIỆU MỚI: {symbol} giá {entry:,.0f}")
                send_telegram(msg)
                
        except Exception as e:
            continue

# ==============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH
# ==============================================================================
if __name__ == "__main__":
    if is_market_hours():
        print("⏰ Đang trong khung giờ giao dịch -> Bắt đầu quét...")
        scan_signals()
    else:
        print("💤 Ngoài khung giờ giao dịch. Bỏ qua lượt quét.")
 
