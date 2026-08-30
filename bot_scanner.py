import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from vnstock import Quote

# --- CẤU HÌNH THÔNG SỐ & API ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_TELEGRAM_CHAT_ID')

BUY_FEE = 0.0015
SELL_FEE = 0.0015
SELL_TAX = 0.0010

HIGH_WINRATE_WATCHLIST = [
    'VIX', 'PNJ', 'DQC', 'BID', 'VRE', 'DGW', 'SSI', 'MBB', 'DGC', 'CTD',
    'PVT', 'LCG', 'YEG', 'TMP', 'FCN', 'VCG', 'SZC', 'IJC', 'TCB', 'TDM',
    'DPR', 'NLG', 'VGT', 'TV2', 'VGC', 'GEX', 'VCI', 'FPT', 'GMD', 'HSG',
    'PLX', 'OCB', 'BVS', 'DHG', 'VHM', 'TCM', 'MBS', 'VSC'
]

def send_telegram_message(message):
    """Hàm gửi tin nhắn cảnh báo qua Telegram"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    if not token or not chat_id or token == 'YOUR_TELEGRAM_BOT_TOKEN':
        print("⚠️ Chưa cấu hình Telegram Token hoặc Chat ID, bỏ qua bước gửi tin nhắn.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Đã gửi tin nhắn Telegram thành công!")
        else:
            print(f"❌ Lỗi gửi Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram: {e}")

def get_market_and_vni_data():
    print("🌐 Đang tải dữ liệu VN-Index và thanh khoản thị trường H1...")
    for src in ["VCI", "TCBS", "KBS"]:
        try:
            quote = Quote(symbol="VNINDEX", source=src)
            df_vni = quote.history(
                start=(datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d"),
                end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval="1H"
            )
            if df_vni is not None and not df_vni.empty:
                df_vni['dt'] = pd.to_datetime(df_vni['time'])
                df_vni = df_vni.sort_values('dt')
                df_vni['VNI_MA20'] = df_vni['close'].rolling(20).mean()
                df_vni['vol_ma20'] = df_vni['volume'].rolling(20).mean()
                print(f"✅ Đã tải thành công dữ liệu thị trường từ nguồn: {src}")
                time.sleep(1.0)
                return df_vni[['dt', 'close', 'volume', 'VNI_MA20', 'vol_ma20']].rename(
                    columns={'close': 'VNI_Close', 'volume': 'VNI_Volume', 'vol_ma20': 'VNI_Vol_MA20'}
                )
        except Exception:
            continue
    print("❌ Không lấy được dữ liệu thị trường!")
    return None

def scan_realtime_signals(symbol, df_vni):
    """Hàm quét tín hiệu MUA thời gian thực tại thời điểm hiện tại"""
    try:
        quote = Quote(symbol=symbol, source="KBS")
        df = quote.history(
            start=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
            end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval="1H"
        )

        if df is None or df.empty or len(df) < 30:
            return None

        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2

        df['tr0'] = df['high'] - df['low']
        df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
        df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()

        df['dt'] = pd.to_datetime(df['time'])
        df = df.sort_values('dt')
        df = pd.merge_asof(df, df_vni, on='dt', direction='backward')

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        vni_trend_ok = (latest['VNI_Close'] > latest['VNI_MA20']) if pd.notnull(latest['VNI_MA20']) else True
        market_liquidity_ok = (latest['VNI_Volume'] >= 0.7 * latest['VNI_Vol_MA20']) if pd.notnull(latest['VNI_Vol_MA20']) else True
        market_ok = vni_trend_ok and market_liquidity_ok

        cross_up = (prev['tenkan'] <= prev['kijun']) and (latest['tenkan'] > latest['kijun'])

        if market_ok and cross_up:
            return {
                "Mã": symbol,
                "Thời gian": str(latest['time']),
                "Giá hiện tại": latest['close'],
                "ATR": latest['atr']
            }
    except Exception as e:
        pass
    return None

def main():
    send_telegram_message("🤖 Test kết nối: Bot Ichimoku đã hoạt động và sẵn sàng trực chiến!")
    print(f"🚀 BẮT ĐẦU QUÉT TÍN HIỆU THỜI GIAN THỰC CHO {len(HIGH_WINRATE_WATCHLIST)} MÃ...")
    df_vni = get_market_and_vni_data()
    print(f"🚀 BẮT ĐẦU QUÉT TÍN HIỆU THỜI GIAN THỰC CHO {len(HIGH_WINRATE_WATCHLIST)} MÃ...")
    df_vni = get_market_and_vni_data()
    if df_vni is None:
        send_telegram_message("⚠️ Bot Ichimoku: Không thể tải dữ liệu thị trường VN-Index lúc khởi chạy.")
        return

    signals = []
    for i, symbol in enumerate(HIGH_WINRATE_WATCHLIST, 1):
        print(f"📡 [{i}/{len(HIGH_WINRATE_WATCHLIST)}] Đang kiểm tra {symbol}...", end="\r")
        res = scan_realtime_signals(symbol, df_vni)
        if res:
            signals.append(res)
        time.sleep(4.0)

    print("\n✅ Quét hoàn tất!")

    if signals:
        msg = "🔥 <b>PHÁT HIỆN TÍN HIỆU MUA (GOLDEN CROSS)</b> 🔥\n\n"
        for sig in signals:
            msg += f"• Mã: <b>{sig['Mã']}</b>\n"
            msg += f"  - Giá: {sig['Giá hiện tại']:,.1f}\n"
            msg += f"  - Thời gian: {sig['Thời gian']}\n\n"
        
        print(msg)
        send_telegram_message(msg)
    else:
        print("ℹ️ Hiện tại không có mã nào kích hoạt điểm mua mới.")
        # Nếu muốn bot báo cáo mỗi lần quét xong dù không có mã (tùy chọn), có thể bật dòng dưới:
        # send_telegram_message("🤖 Bot Ichimoku đã quét xong phiên này, hiện tại chưa phát hiện mã nào kích hoạt điểm mua.")

if __name__ == "__main__":
    main()
 
