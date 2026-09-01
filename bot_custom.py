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
# 1. CẤU HÌNH BOT TELEGRAM & THAM SỐ TỐI ƯU CỦA MSR & VTP
# ==============================================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

CONFIGS = {
    'MSR': {
        'sl_mult': 4.0,
        'tp_mult': 7.0,
        'holding_bars': 20,
        'pullback': 0.02,
        'use_ma100_filter': True,
    },
    'VTP': {
        'sl_mult': 3.3,
        'tp_mult': 4.0,
        'holding_bars': 12,
        'pullback': 0.03,
        'use_ma100_filter': False,
    }
}

# ==============================================================================
# 2. HÀM TƯƠNG TÁC TELEGRAM & GIỜ GIAO DỊCH
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
# 3. TÍNH TOÁN CHỈ BÁO KỸ THUẬT
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
    
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['ma100'] = df['close'].rolling(100).mean()
    return df

# ==============================================================================
# 4. HÀM QUÉT TÍN HIỆU RIÊNG CHO MSR & VTP
# ==============================================================================
def scan_custom_stocks():
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_str = datetime.now(tz_vn).strftime("%H:%M:%S %d/%m/%Y")
    print(f"\n🔍 [{now_str}] Bắt đầu quét tín hiệu tối ưu MSR & VTP...")

    for symbol, cfg in CONFIGS.items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start="2026-01-01", interval="1H")
            if df is None or len(df) < 110:
                continue

            df = calculate_indicators(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]

            # 1. Bộ lọc MA100 (Nếu kích hoạt)
            if cfg['use_ma100_filter'] and (pd.isna(curr['ma100']) or curr['close'] <= curr['ma100']):
                continue

            # 2. Bộ lọc Xu hướng MA20 > MA50 & Ichimoku
            if pd.isna(curr['ma20']) or pd.isna(curr['ma50']) or curr['ma20'] <= curr['ma50']:
                continue

            # Tín hiệu Tenkan cắt lên Kijun
            cross_up = (prev['tenkan'] <= prev['kijun']) and (curr['tenkan'] > curr['kijun'])
            if not cross_up:
                continue

            # 3. Bộ lọc Pullback (Độ nén sát đường MA20)
            price_vs_ma20 = curr['close'] / curr['ma20']
            if not ((1 - cfg['pullback']) <= price_vs_ma20 <= (1 + cfg['pullback'])):
                continue

            atr = curr['atr']
            if pd.isna(atr) or atr == 0:
                continue

            entry = curr['close']
            sl = entry - (cfg['sl_mult'] * atr)
            tp = entry + (cfg['tp_mult'] * atr)
            days_holding = cfg['holding_bars'] / 4.0

            msg = (
                f"⭐ <b>[TÍN HIỆU TỐI ƯU RIÊNG - #{symbol}]</b> ⭐\n\n"
                f"📌 <b>Mã CP:</b> #{symbol}\n"
                f"💵 <b>Giá Mua (Entry):</b> {entry:,.0f} VND\n"
                f"🎯 <b>Chốt lời (TP {cfg['tp_mult']}x ATR):</b> {tp:,.0f} VND (+{((tp/entry)-1)*100:.1f}%)\n"
                f"🛡 <b>Cắt lỗ (SL {cfg['sl_mult']}x ATR):</b> {sl:,.0f} VND (-{((1-(sl/entry)))*100:.1f}%)\n"
                f"⏱ <b>Thời gian nắm giữ:</b> {cfg['holding_bars']} nến H1 (~{days_holding:.1f} ngày)\n"
                f"📊 <b>Quy tắc Martingale:</b> Tăng +50% vốn nếu lệnh trước thắng (Max 15%)\n"
                f"🕒 <b>Nến phát hiện:</b> {curr['time']}"
            )

            print(f"✅ PHÁT HIỆN TÍN HIỆU {symbol} tại giá {entry:,.0f}")
            send_telegram(msg)

        except Exception as e:
            print(f"❌ Lỗi khi quét {symbol}: {e}")

# ==============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH (CHẠY 1 LẦN CHO GITHUB ACTIONS)
# ==============================================================================
if __name__ == "__main__":
    if is_market_hours():
        print("⏰ Đang trong khung giờ giao dịch -> Bắt đầu quét...")
        scan_custom_stocks()
    else:
        print("💤 Ngoài khung giờ giao dịch. Bỏ qua lượt quét MSR/VTP.")
 
