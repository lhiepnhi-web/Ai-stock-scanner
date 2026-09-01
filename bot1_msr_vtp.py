"""
===============================================================================================
BOT MSR & VTP ULTIMATE PRODUCTION v3.3 (GITHUB READY)
===============================================================================================
Author: Quantitative Trading System
Description: Automated backtesting and production-ready trading script for MSR and VTP 
             incorporating realistic slippage, transaction fees, trailing lock mechanisms, 
             and portfolio drawdown protection guards.
===============================================================================================
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import Quote
import warnings

# Suppress minor warnings for clean execution logs
warnings.filterwarnings('ignore')

# ==============================================================================
# GLOBAL CONFIGURATION & RISK MANAGEMENT PARAMETERS
# ==============================================================================
INIT_CAPITAL = 1_000_000_000  # Initial Portfolio Capital: 1 Billion VND
ALLOC_PER_TRADE = 0.40        # Capital allocation per position: 40% NAV
FEE_BUY = 0.0015              # Brokerage fee on buy: 0.15%
FEE_SELL = 0.0025             # Brokerage fee + tax on sell: 0.25%
TOTAL_FEE = FEE_BUY + FEE_SELL # Total round-trip fee: 0.40%
SLIPPAGE = 0.0010             # Execution slippage buffer: 0.10%
MAX_PORTFOLIO_DD = 0.08       # Hard stop: Halt system if portfolio drawdown exceeds 8%

MSR_VTP_CONFIG = {
    'name': 'Bot MSR & VTP Ultimate Production v3.3',
    'symbols': {
        'MSR': {
            'atr_mult': 1.5, 
            'max_sl': 3.0, 
            'tp': 7.5, 
            'holding': 12, 
            'rsi_thresh': 35, 
            'trail_trigger': 1.025, 
            'trail_offset': 0.012
        },
        'VTP': {
            'atr_mult': 1.5, 
            'max_sl': 2.5, 
            'tp': 9.2, 
            'holding': 15, 
            'rsi_thresh': 38, 
            'trail_trigger': 1.025, 
            'trail_offset': 0.012
        },
    }
}

def calculate_indicators(df):
    """
    Calculates technical indicators required for entry and exit signals:
    - EMA 20 (Short-term trend / reversion reference)
    - 20-period Low (Breakout/support boundary)
    - RSI 14 (Oversold momentum filter)
    - ATR 14 (Volatility metric for dynamic stop-loss positioning)
    """
    df = df.copy()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['low_20'] = df['low'].shift(1).rolling(20).min()
    
    # Relative Strength Index (RSI 14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    
    # Average True Range (ATR 14)
    df['tr0'] = df['high'] - df['low']
    df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
    df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].rolling(14).mean()
    
    return df

def run_production_bot_v33():
    """
    Executes the backtest simulation across specified tickers with production constraints.
    Outputs trade log metrics and exports results to CSV.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print("="*95)
    print(f"🚀 INITIALIZING {MSR_VTP_CONFIG['name'].upper()}")
    print("="*95)
    
    all_trades = []
    current_nav = INIT_CAPITAL
    peak_nav = INIT_CAPITAL
    system_halted = False
    
    for symbol, cfg in MSR_VTP_CONFIG['symbols'].items():
        if system_halted:
            break
            
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(start=start_str, end=end_str, interval="1D")
            if df is None or len(df) < 50: 
                continue
            
            df = calculate_indicators(df)
            in_position = False
            entry_price, sl_price, tp_price = 0, 0, 0
            peak_price = 0
            trailing_activated = False
            holding_count = 0
            entry_time = None
            cooldown_bars = 0
            
            i = 25
            while i < len(df) - 1 and not system_halted:
                curr = df.iloc[i]
                
                if cooldown_bars > 0:
                    cooldown_bars -= 1
                
                if in_position:
                    holding_count += 1
                    
                    if curr['high'] > peak_price:
                        peak_price = curr['high']
                    
                    # Activate Trailing Lock when price hits trigger threshold
                    if not trailing_activated and peak_price >= entry_price * cfg['trail_trigger']:
                        trailing_activated = True
                        sl_price = max(sl_price, entry_price)
                    
                    if trailing_activated:
                        new_trail_sl = peak_price * (1.0 - cfg['trail_offset'])
                        if new_trail_sl > sl_price:
                            sl_price = new_trail_sl
                    
                    hit_tp = curr['high'] >= tp_price
                    hit_sl = curr['low'] <= sl_price
                    revert_ema = curr['close'] >= curr['ema20']
                    time_out = holding_count >= cfg['holding']
                    
                    if hit_tp:
                        exit_price = tp_price * (1.0 - SLIPPAGE)
                        reason = "Chốt Lời (TP)"
                        hit_exit = True
                    elif hit_sl:
                        exit_price = sl_price * (1.0 - SLIPPAGE)
                        reason = "Trailing Lock" if trailing_activated else "Cắt Lỗ Capped (SL)"
                        hit_exit = True
                        cooldown_bars = 3
                    elif revert_ema and holding_count >= 4:
                        exit_price = curr['close'] * (1.0 - SLIPPAGE)
                        reason = "Hồi về EMA20"
                        hit_exit = True
                    elif time_out:
                        exit_price = curr['close'] * (1.0 - SLIPPAGE)
                        reason = "Hết Thời Hạn"
                        hit_exit = True
                    else:
                        hit_exit = False
                    
                    if hit_exit:
                        raw_pnl = (exit_price - entry_price) / entry_price
                        net_pnl = raw_pnl - TOTAL_FEE
                        trade_value = current_nav * ALLOC_PER_TRADE
                        pnl_vnd = trade_value * net_pnl
                        
                        current_nav += pnl_vnd
                        if current_nav > peak_nav:
                            peak_nav = current_nav
                        
                        # Portfolio-wide drawdown guard check
                        current_dd = (peak_nav - current_nav) / peak_nav
                        if current_dd >= MAX_PORTFOLIO_DD:
                            system_halted = True
                            reason += " [SYSTEM HALTED: MAX DRAWDOWN REACHED]"
                        
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
                    if cooldown_bars > 0:
                        i += 1
                        continue
                        
                    oversold_rsi = curr['rsi'] < cfg['rsi_thresh']
                    touch_low = curr['low'] <= curr['low_20'] * 1.02
                    green_candle = curr['close'] > curr['open']
                    
                    if oversold_rsi and touch_low and green_candle and pd.notnull(curr['atr']) and curr['atr'] > 0:
                        next_bar = df.iloc[i + 1]
                        in_position = True
                        entry_price = next_bar['open'] * (1.0 + SLIPPAGE)
                        peak_price = entry_price
                        
                        sl_atr_dist = curr['atr'] * cfg['atr_mult']
                        sl_fixed_dist = entry_price * (cfg['max_sl'] / 100.0)
                        final_sl_dist = min(sl_atr_dist, sl_fixed_dist)
                        
                        sl_price = entry_price - final_sl_dist
                        tp_price = entry_price * (1.0 + cfg['tp'] / 100.0)
                        trailing_activated = False
                        holding_count = 0
                        entry_time = next_bar['time']
                        i += 1 
                        
                i += 1
                        
        except Exception as e:
            print(f"Error processing symbol {symbol}: {e}")
            continue

    df_trades = pd.DataFrame(all_trades)
    if df_trades.empty:
        print("⚠️ No trades generated.")
        return

    # Export structured trade logs to CSV for tracking
    df_trades.to_csv("msr_vtp_production_v33_log.csv", index=False, encoding="utf-8-sig")

    total_pnl = df_trades['pnl_raw'].sum()
    win_trades = df_trades[df_trades['pnl_raw'] > 0]
    win_rate = (len(win_trades) / len(df_trades)) * 100
    
    cols_display = ['Mã', 'Vào lệnh', 'Giá Mua', 'Giá Bán', 'Lãi/Lỗ ròng (%)', 'Lãi/Lỗ (VND)', 'Lý do']
    print(df_trades[cols_display].to_string(index=False))
    
    print("\n" + "="*95)
    print("📊 PERFORMANCE SUMMARY REPORT (ULTIMATE v3.3)")
    print("="*95)
    print(f"🔹 Total Trades Executed  : {len(df_trades)}")
    print(f"🔹 Winning / Losing Trades: {len(win_trades)} wins / {len(df_trades)-len(win_trades)} losses")
    print(f"🔹 Win Rate               : {win_rate:.1f}%")
    print(f"💵 Total Net Profit       : {total_pnl:+,.0f} VND")
    print(f"📈 NAV Growth             : {((current_nav - INIT_CAPITAL) / INIT_CAPITAL) * 100:+.2f}%")
    print(f"💾 Trade Log Exported To  : msr_vtp_production_v33_log.csv")
    print("="*95)

if __name__ == "__main__":
    run_production_bot_v33()
 
