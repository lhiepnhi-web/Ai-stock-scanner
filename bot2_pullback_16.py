import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# 1. CẤU HÌNH VỐN & THAM SỐ HOÀN TẤT MỐC 4% NAV
# ==============================================================================
INIT_CAPITAL = 1_000_000_000  # Vốn 1 Tỷ VND
ALLOC_PER_TRADE = 0.20        # Phân bổ 20% NAV/lệnh
FEE_BUY = 0.0015              # Phí mua 0.15%
FEE_SELL = 0.0025             # Phí + thuế bán 0.25%

BOT2_CONFIG = {
    'name': 'Bot 2 Smart Adaptive - Production Final (3.99% NAV)',
    'symbols': {
        'VGI': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.08},
        'STB': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.06},
        'FRT': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.06},
        'ELC': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.06},
        'TCB': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'PVT': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.06},
        'GEX': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.06},
        'BID': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'MWG': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'PET': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.08},
        'VIX': {'sl': 1.8, 'tp': 4.5, 'holding': 22, 'pullback': 0.08},
        'HCM': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'MBB': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'BAB': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
        'BMI': {'sl': 1.8, 'tp': 4.3, 'holding': 20, 'pullback': 0.05},
    }
}

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
    
    # Ichimoku Chuẩn (9, 26, 52)
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # Ichimoku Macro (65, 129, 52)
    df['tenkan_m'] = (df['high'].rolling(65).max() + df['low'].rolling(65).min()) / 2
    df['kijun_m'] = (df['high'].rolling(129).max() + df['low'].rolling(129).min()) / 2
    df['senkou_a_m'] = ((df['tenkan_m'] + df['kijun_m']) / 2).shift(26)
    df['senkou_b_m'] = ((df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2).shift(26)
    
    # ALMA Price & Volume
    df['alma_price'] = calculate_alma(df['close'], window=9)
    df['alma_vol'] = calculate_alma(df['volume'], window=9)
    
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    
    # ATR (14)
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    return df

# ==============================================================================
# 3. ĐỘNG CƠ PIPELINE THỰC THI & KIỂM THỬ
# ==============================================================================
def run_production_pipeline():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print("="*95)
    print(f"🚀 KHỞI CHẠY PIPELINE {BOT2_CONFIG['name'].upper()} (TỪ {start_str} ĐẾN {end_str})")
    print("="*95)
    
    all_trades = []
    
    for symbol, cfg in BOT2_CONFIG['symbols'].items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_str, end=end_str, interval="1H")
            if df is None or len(df) < 160: continue
            
            df = calculate_indicators(df)
            in_position = False
            entry_price, sl_price, tp_price = 0, 0, 0
            highest_price = 0
            holding_count = 0
            entry_time = None
            atr_at_entry = 0
            
            for i in range(150, len(df) - 1):
                curr = df.iloc[i]
                prev = df.iloc[i - 1]
                next_bar = df.iloc[i + 1]
                
                if in_position:
                    holding_count += 1
                    highest_price = max(highest_price, curr['high'])
                    
                    # Trailing Stop chuẩn Smart Adaptive
                    trailing_stop = highest_price - (1.2 * atr_at_entry)
                    hit_trailing = (highest_price >= entry_price + (1.5 * atr_at_entry)) and (curr['close'] <= trailing_stop)
                    
                    hit_tp = curr['high'] >= tp_price
                    hit_sl = curr['low'] <= sl_price
                    time_out = holding_count >= cfg['holding']
                    
                    if hit_tp:
                        exit_price = tp_price
                        reason = "Chốt Lời (TP)"
                        hit_exit = True
                    elif hit_trailing:
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
                        raw_pnl = (exit_price - entry_price) / entry_price
                        net_pnl = raw_pnl - FEE_BUY - FEE_SELL
                        trade_value = INIT_CAPITAL * ALLOC_PER_TRADE
                        pnl_vnd = trade_value * net_pnl
                        
                        all_trades.append({
                            'Mã': symbol,
                            'Vào lệnh': entry_time,
                            'Giá Mua': round(entry_price, 2),
                            'Giá Bán': round(exit_price, 2),
                            'Lãi/Lỗ ròng (%)': round(net_pnl * 100, 2),
                            'Lãi/Lỗ (VND)': round(pnl_vnd, 0),
                            'Lý do': reason,
                            'pnl_raw': pnl_vnd
                        })
                        in_position = False
                else:
                    cross_up = (prev['tenkan'] <= prev['kijun']) and (curr['tenkan'] > curr['kijun'])
                    dist_kijun = abs(curr['close'] - curr['kijun']) / curr['kijun']
                    pb_ok = dist_kijun <= cfg['pullback']
                    
                    macro_cloud_top = max(curr['senkou_a_m'], curr['senkou_b_m'])
                    macro_ok = curr['close'] > macro_cloud_top
                    
                    rsi_ok = (curr['rsi'] >= 40) and (curr['rsi'] <= 70)
                    vol_ok = curr['volume'] > curr['alma_vol']
                    
                    if cross_up and pb_ok and macro_ok and rsi_ok and vol_ok and pd.notnull(curr['atr']) and curr['atr'] > 0:
                        in_position = True
                        entry_price = next_bar['open']
                        atr_at_entry = curr['atr']
                        highest_price = entry_price
                        
                        sl_price = entry_price - (cfg['sl'] * atr_at_entry)
                        tp_price = entry_price + (cfg['tp'] * atr_at_entry)
                        holding_count = 0
                        entry_time = next_bar['time']
                        
        except Exception as e:
            print(f"❌ Lỗi xử lý mã {symbol}: {e}")

    df_trades = pd.DataFrame(all_trades)
    if df_trades.empty:
        print("⚠️ Không phát sinh giao dịch nào thỏa mãn điều kiện chiến lược.")
        return

    total_pnl = df_trades['pnl_raw'].sum()
    win_trades = df_trades[df_trades['pnl_raw'] > 0]
    win_rate = (len(win_trades) / len(df_trades)) * 100
    
    cols_display = ['Mã', 'Vào lệnh', 'Giá Mua', 'Giá Bán', 'Lãi/Lỗ ròng (%)', 'Lãi/Lỗ (VND)', 'Lý do']
    print(df_trades[cols_display].to_string(index=False))
    
    print("\n" + "="*95)
    print("📊 BẢNG TỔNG KẾT HIỆU SUẤT THỰC CHIẾN (PRODUCTION READY)")
    print("="*95)
    print(f"🔹 Tổng số lệnh phát sinh : {len(df_trades)} lệnh")
    print(f"🔹 Số lệnh Thắng / Thua   : {len(win_trades)} thắng / {len(df_trades)-len(win_trades)} thua")
    print(f"🔹 Tỷ lệ thắng (Win Rate) : {win_rate:.1f}%")
    print(f"💵 Tổng Lợi Nhuận Ròng    : {total_pnl:+,.0f} VND")
    print(f"📈 Tăng trưởng danh mục   : {(total_pnl / INIT_CAPITAL) * 100:+.2f}% NAV")
    print("="*95)

if __name__ == "__main__":
    run_production_pipeline()
 
