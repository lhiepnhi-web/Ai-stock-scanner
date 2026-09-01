import os
import requests
import warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import Quote

warnings.filterwarnings('ignore')

# ==============================================================================
# 1. CẤU HÌNH THAM SỐ CHUẨN VẬN HÀNH (+4.38% NAV)
# ==============================================================================
INIT_CAPITAL = 1_000_000_000  # Vốn ban đầu 1 Tỷ VND
FIXED_NAV_PCT = 0.15          # Đi cố định 15% NAV / lệnh
FEE_BUY = 0.0015              # Phí mua 0.15%
FEE_SELL = 0.0025             # Phí + thuế bán 0.25% (Tổng ròng 0.4%)
SYMBOLS = ['MSR', 'VTP']        # Danh mục cốt lõi tối ưu

# Cấu hình Telegram (Lấy từ biến môi trường trên GitHub Secrets hoặc điền trực tiếp)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")


# ==============================================================================
# 2. HÀM TÍNH CHỈ BÁO KỸ THUẬT
# ==============================================================================
def calculate_alma(series, window=9, sigma=6, offset=0.85):
    m = offset * (window - 1)
    s = window / sigma
    d_w = np.exp(-((np.arange(window) - m) ** 2) / (2 * s * s))
    weights = d_w / d_w.sum()
    return series.rolling(window).apply(lambda x: np.dot(x, weights), raw=True)

def calculate_indicators(df):
    df = df.copy()
    # Đường trung bình động
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['alma'] = calculate_alma(df['close'], window=9, sigma=6, offset=0.85)
    df['alma_slope'] = df['alma'] - df['alma'].shift(2)
    
    # Volume MA
    df['vol_ma'] = df['volume'].rolling(20).mean()
    
    # RSI (Wilder EWM)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Ichimoku
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # ATR (14)
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df


# ==============================================================================
# 3. HÀM GỬI CẢNH BÁO TELEGRAM
# ==============================================================================
def send_telegram(message):
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or not TELEGRAM_TOKEN:
        print("⚠️ Chưa cấu hình Telegram Token. Bỏ qua gửi tin nhắn.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("🚀 Đã gửi thông báo Telegram thành công!")
        else:
            print(f"❌ Lỗi Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram API: {e}")


# ==============================================================================
# 4. BACKTEST CHUẨN BẢO TỒN VỐN (+4.38% NAV)
# ==============================================================================
def run_backtest():
    print("="*85)
    print("🔄 ĐANG CHẠY BACKTEST HỆ THỐNG 15% NAV...")
    print("="*85)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    all_trades = []
    
    for symbol in SYMBOLS:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_str, end=end_str, interval="1H")
            if df is None or len(df) < 100: continue
            
            df = calculate_indicators(df)
            in_position = False
            entry_price, sl_price, tp_price = 0, 0, 0
            highest_price = 0
            holding_count = 0
            entry_time = None
            atr_at_entry = 0
            breakeven_triggered = False
            
            for i in range(50, len(df) - 1):
                curr = df.iloc[i]
                next_bar = df.iloc[i + 1]
                
                if in_position:
                    holding_count += 1
                    highest_price = max(highest_price, curr['high'])
                    
                    if not breakeven_triggered and (highest_price >= entry_price + 1.8 * atr_at_entry):
                        sl_price = max(sl_price, entry_price * 1.005)
                        breakeven_triggered = True
                    
                    trailing_stop = highest_price - (1.5 * atr_at_entry)
                    is_trailing_hit = (highest_price >= entry_price + 2.5 * atr_at_entry) and (curr['close'] <= trailing_stop)
                    
                    hit_tp = curr['high'] >= tp_price
                    hit_sl = curr['low'] <= sl_price
                    time_out = holding_count >= 20
                    
                    if hit_tp:
                        exit_price = tp_price
                        reason = "Chốt Lời (TP)"
                        hit_exit = True
                    elif is_trailing_hit:
                        exit_price = trailing_stop
                        reason = "Trailing Stop"
                        hit_exit = True
                    elif hit_sl:
                        exit_price = sl_price
                        reason = "Cắt Lỗ (SL)"
                        hit_exit = True
                    elif time_out:
                        exit_price = curr['close']
                        reason = "Hết T+"
                        hit_exit = True
                    else:
                        hit_exit = False
                    
                    if hit_exit:
                        raw_pnl_pct = (exit_price - entry_price) / entry_price
                        net_pnl_pct = raw_pnl_pct - FEE_BUY - FEE_SELL
                        allocated_capital = INIT_CAPITAL * FIXED_NAV_PCT
                        pnl_vnd = allocated_capital * net_pnl_pct
                        
                        all_trades.append({
                            'Mã': symbol,
                            'Vào lệnh': entry_time,
                            'Giá Mua': round(entry_price, 2),
                            'Giá Bán': round(exit_price, 2),
                            'Vốn Đi (%NAV)': f"{FIXED_NAV_PCT*100:.1f}%",
                            'Lãi/Lỗ ròng (%)': round(net_pnl_pct * 100, 2),
                            'Lãi/Lỗ (VND)': f"{pnl_vnd:+,.0f}",
                            'Lý do': reason,
                            'pnl_raw': pnl_vnd
                        })
                        in_position = False
                else:
                    trend_ok = (curr['close'] > curr['alma']) and (curr['alma_slope'] > 0) and (curr['close'] > curr['ma50'])
                    ma_align = (curr['ma10'] > curr['ma20']) and (curr['tenkan'] >= curr['kijun'])
                    rsi_ok = (curr['rsi'] >= 45) and (curr['rsi'] <= 62)
                    vol_ok = curr['volume'] > (curr['vol_ma'] * 1.25)
                    
                    if trend_ok and ma_align and rsi_ok and vol_ok and pd.notnull(curr['atr']) and curr['atr'] > 0:
                        in_position = True
                        entry_price = next_bar['open']
                        highest_price = entry_price
                        atr_at_entry = curr['atr']
                        
                        sl_price = entry_price - (2.0 * atr_at_entry)
                        tp_price = entry_price + (4.5 * atr_at_entry)
                        
                        holding_count = 0
                        entry_time = next_bar['time']
                        breakeven_triggered = False
                        
        except Exception as e:
            print(f"❌ Lỗi {symbol}: {e}")

    df_trades = pd.DataFrame(all_trades)
    if not df_trades.empty:
        total_pnl = df_trades['pnl_raw'].sum()
        win_trades = df_trades[df_trades['pnl_raw'] > 0]
        
        cols = ['Mã', 'Vào lệnh', 'Giá Mua', 'Giá Bán', 'Vốn Đi (%NAV)', 'Lãi/Lỗ ròng (%)', 'Lãi/Lỗ (VND)', 'Lý do']
        print(df_trades[cols].to_string(index=False))
        print("\n" + "="*85)
        print(f"📊 Win Rate: {(len(win_trades)/len(df_trades))*100:.1f}% | Lợi Nhuận: {total_pnl:+,.0f} VND ({(total_pnl / INIT_CAPITAL) * 100:+.2f}% NAV)")
        print("="*85)


# ==============================================================================
# 5. QUÉT TÍN HIỆU THỰC CHIẾN (LIVE SCANNER)
# ==============================================================================
def run_live_scanner():
    print(f"\n🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ĐANG QUÉT TÍN HIỆU THỰC CHIẾN...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    for symbol in SYMBOLS:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'), interval="1H")
            if df is None or len(df) < 50: continue
            
            df = calculate_indicators(df)
            curr = df.iloc[-1] # Nến mới nhất vừa đóng
            
            trend_ok = (curr['close'] > curr['alma']) and (curr['alma_slope'] > 0) and (curr['close'] > curr['ma50'])
            ma_align = (curr['ma10'] > curr['ma20']) and (curr['tenkan'] >= curr['kijun'])
            rsi_ok = (curr['rsi'] >= 45) and (curr['rsi'] <= 62)
            vol_ok = curr['volume'] > (curr['vol_ma'] * 1.25)
            
            if trend_ok and ma_align and rsi_ok and vol_ok:
                entry_est = curr['close']
                sl_est = entry_est - (2.0 * curr['atr'])
                tp_est = entry_est + (4.5 * curr['atr'])
                vol_ratio = (curr['volume'] / curr['vol_ma']) * 100
                
                msg = (
                    f"🚨 **TÍN HIỆU MUA THỰC CHIẾN: {symbol}** 🚨\n\n"
                    f"⏱ **Thời gian:** {curr['time']}\n"
                    f"💵 **Giá vào lệnh (Khuyên dùng):** {entry_est:,.2f}\n"
                    f"🛑 **Cắt lỗ (SL -2.0 ATR):** {sl_est:,.2f}\n"
                    f"🎯 **Chốt lời (TP +4.5 ATR):** {tp_est:,.2f}\n"
                    f"📊 **Vốn khuyến nghị:** 15% NAV\n"
                    f"🔥 **Xác nhận Vôn:** {vol_ratio:.0f}% so với trung bình\n"
                    f"📈 **RSI:** {curr['rsi']:.1f}\n"
                )
                print(msg)
                send_telegram(msg)
            else:
                print(f"ℹ️ {symbol}: Chưa có tín hiệu đạt chuẩn.")
        except Exception as e:
            print(f"❌ Lỗi quét {symbol}: {e}")

if __name__ == "__main__":
    run_backtest()
    run_live_scanner()
 
