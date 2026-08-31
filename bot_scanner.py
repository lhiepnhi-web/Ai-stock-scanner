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
TELEGRAM_TOKEN = "8517494324:AAFxYulrkSy1lhftzejbCFPmEv-cmpt5utc "  # Thay bằng Token từ @BotFather
TELEGRAM_CHAT_ID = "6760219447 "  # Thay bằng Chat ID của bạn

WATCHLIST = [
    'VIX', 'PNJ', 'DGW', 'PVT', 'DQC', 'LCG', 'DIG', 'TCB', 'YEG', 'BID', 
    'TPB', 'TDM', 'FCN', 'TV2', 'VSC', 'VRE', 'MBB', 'PET', 'TMP', 'CTG', 
    'HDB', 'IJC', 'SAB', 'PC1', 'SSI', 'BFC', 'HSG', 'BMI', 'CTD', 'DPR', 
    'VNM', 'VCG', 'NLG', 'GMD', 'GEX', 'PLX', 'CII', 'CTS', 'AAA', 'VPB', 
    'VHM', 'NTP', 'SZC', 'HCM', 'PDR', 'FTS', 'DGC', 'MBS'
]
WATCHLIST = list(dict.fromkeys(WATCHLIST))

# Lưu vết các tín hiệu đã gửi để tránh bắn lặp tin nhắn trong cùng 1 nến H1
SENT_SIGNALS = set()

# ==============================================================================
# 2. HÀM TƯƠNG TÁC TELEGRAM
# ==============================================================================
def send_telegram(message):
    """Hàm gửi tin nhắn qua Telegram Bot API"""
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

def test_telegram_connection():
    """Kiểm tra kết nối Telegram khi khởi chạy script"""
    print("📡 Đang kết nối tới Telegram Bot...")
    tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
    now_str = datetime.now(tz_vn).strftime("%H:%M:%S %d/%m/%Y")
    
    test_msg = (
        "🤖 <b>[KẾT NỐI THÀNH CÔNG]</b>\n"
        f"⏱ Thời gian: {now_str}\n"
        "✅ Bot tín hiệu Ichimoku T+2.5 đã sẵn sàng hoạt động!"
    )
    if send_telegram(test_msg):
        print("✅ Gửi tin nhắn test Telegram thành công!")
    else:
        print("❌ Kết nối Telegram thất bại! Vui lòng kiểm tra lại TOKEN và CHAT_ID.")

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
    print(f"\n🔍 [{datetime.now().strftime('%H:%M:%S')}] Đang quét tín hiệu thị trường...")
    
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
                signal_id = f"{symbol}_{curr['time']}"
                
                if signal_id not in SENT_SIGNALS:
                    entry_price = curr['close']
                    sl_price = entry_price - (2.0 * curr['atr'])
                    tp_price = entry_price + (4.5 * curr['atr'])
                    
                    # Soạn nội dung tin nhắn Telegram
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
                    if send_telegram(msg):
                        SENT_SIGNALS.add(signal_id)
        except Exception as e:
            continue

# ==============================================================================
# 5. CHƯƠNG TRÌNH CHÍNH (MAIN LOOP)
# ==============================================================================
if __name__ == "__main__":
    # 1. Gửi tin nhắn test kết nối
    test_telegram_connection()
    
    print("\n🚀 Bot quét tín hiệu thực chiến bắt đầu vận hành...")
    print("⏰ Giờ hoạt động: 09:00-11:30 & 13:00-14:30 (Thứ 2 - Thứ 6)\n")
    
    # 2. Vòng lặp quét dữ liệu mỗi 5 phút/lần
    while True:
        if is_market_hours():
            scan_signals()
        else:
            tz_vn = pytz.timezone('Asia/Ho_Chi_Minh')
            now_str = datetime.now(tz_vn).strftime("%H:%M:%S")
            print(f"\r💤 [{now_str}] Ngoài giờ giao dịch. Bot đang nghỉ...", end="")
            
        time.sleep(300) # Quét lại sau 5 phút (300 giây)
 
