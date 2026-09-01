import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import Quote
import warnings
warnings.filterwarnings('ignore')

# ==============================================================================
# CẤU HÌNH BOT 6.5: MEAN REVERSION ULTIMATE (+10.53% NAV)
# ==============================================================================
INIT_CAPITAL = 1_000_000_000  # Vốn khởi điểm: 1 Tỷ VND
ALLOC_PER_TRADE = 0.22        # Phân bổ 22% NAV mỗi lệnh
FEE_BUY = 0.0015              # Phí mua: 0.15%
FEE_SELL = 0.0025             # Phí + thuế bán: 0.25%
TOTAL_FEE = FEE_BUY + FEE_SELL # Tổng chi phí giao dịch: 0.40%

BOT65_CONFIG = {
    'name': 'Bot 6.5 Mean Reversion Ultimate',
    'symbols': {
        'STB': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'FPT': {'sl': 1.7, 'tp': 5.0, 'holding': 15},
        'MWG': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'GMD': {'sl': 2.2, 'tp': 5.0, 'holding': 15},
        'DGC': {'sl': 2.7, 'tp': 6.5, 'holding': 20},
        'SSI': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
        'GAS': {'sl': 2.7, 'tp': 6.0, 'holding': 15},
        'KBC': {'sl': 2.2, 'tp': 5.5, 'holding': 15},
    }
}

def calculate_indicators(df):
    df = df.copy()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['low_20'] = df['low'].shift(1).rolling(20).min()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def run_backtest_ultimate():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print("="*95)
    print(f"🚀 Đang chạy Backtest {BOT65_CONFIG['name'].upper()}...")
    print("="*95)
    
    all_trades = []
    
    for symbol, cfg in BOT65_CONFIG['symbols'].items():
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_str, end=end_str, interval="1D")
            if df is None or len(df) < 50: continue
            
            df = calculate_indicators(df)
            in_position = False
            entry_price, sl_price, tp_price = 0, 0, 0
            holding_count = 0
            entry_time = None
            
            i = 25
            while i < len(df) - 1:
                curr = df.iloc[i]
                
                if in_position:
                    holding_count += 1
                    
                    hit_tp = curr['high'] >= tp_price
                    hit_sl = curr['low'] <= sl_price
                    revert_ema = curr['close'] >= curr['ema20']
                    time_out = holding_count >= cfg['holding']
                    
                    if hit_tp:
                        exit_price = tp_price
                        reason = "Chốt Lời (TP)"
                        hit_exit = True
                    elif revert_ema and holding_count >= 2:
                        exit_price = curr['close']
                        reason = "Hồi về EMA20"
                        hit_exit = True
                    elif hit_sl:
                        exit_price = sl_price
                        reason = "Cắt Lỗ (SL)"
                        hit_exit = True
                    elif time_out:
                        exit_price = curr['close']
                        reason = "Hết Thời Hạn"
                        hit_exit = True
                    else:
                        hit_exit = False
                    
                    if hit_exit:
                        raw_pnl = (exit_price - entry_price) / entry_price
                        net_pnl = raw_pnl - TOTAL_FEE
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
                    oversold_rsi = curr['rsi'] < 33
                    touch_low = curr['low'] <= curr['low_20'] * 1.02
                    
                    if oversold_rsi and touch_low and pd.notnull(curr['atr']) and curr['atr'] > 0:
                        next_bar = df.iloc[i + 1]
                        in_position = True
                        entry_price = next_bar['open']
                        
                        sl_price = entry_price * (1.0 - cfg['sl'] / 100.0)
                        tp_price = entry_price * (1.0 + cfg['tp'] / 100.0)
                        holding_count = 0
                        entry_time = next_bar['time']
                        i += 1 
                        
                i += 1
                        
        except Exception as e:
            continue

    df_trades = pd.DataFrame(all_trades)
    if df_trades.empty:
        print("⚠️ Không phát sinh giao dịch nào.")
        return

    total_pnl = df_trades['pnl_raw'].sum()
    win_trades = df_trades[df_trades['pnl_raw'] > 0]
    win_rate = (len(win_trades) / len(df_trades)) * 100
    
    cols_display = ['Mã', 'Vào lệnh', 'Giá Mua', 'Giá Bán', 'Lãi/Lỗ ròng (%)', 'Lãi/Lỗ (VND)', 'Lý do']
    print(df_trades[cols_display].to_string(index=False))
    
    print("\n" + "="*95)
    print("📊 BẢNG TỔNG KẾT HIỆU SUẤT BOT 6.5 MEAN REVERSION ULTIMATE")
    print("="*95)
    print(f"🔹 Tổng số lệnh phát sinh : {len(df_trades)} lệnh")
    print(f"🔹 Số lệnh Thắng / Thua   : {len(win_trades)} thắng / {len(df_trades)-len(win_trades)} thua")
    print(f"🔹 Tỷ lệ thắng (Win Rate) : {win_rate:.1f}%")
    print(f"💵 Tổng Lợi Nhuận Ròng    : {total_pnl:+,.0f} VND")
    print(f"📈 Tăng trưởng danh mục   : {(total_pnl / INIT_CAPITAL) * 100:+.2f}% NAV")
    print("="*95)

if __name__ == "__main__":
    run_backtest_ultimate()
