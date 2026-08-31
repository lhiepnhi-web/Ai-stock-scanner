# ============================================
# BACKTEST CHỈ MÃ CÓ LỜI - GIAI ĐOẠN 2 THÁNG (6/2026 - 8/2026)
# KÈM TÍNH NĂNG BÁO CÁO QUA TELEGRAM
# ============================================

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from vnstock import Quote
from tabulate import tabulate
import warnings
warnings.filterwarnings('ignore')

BUY_FEE = 0.0015
SELL_FEE = 0.0015
SELL_TAX = 0.0010

# ============================================
# 44 MÃ CÓ LỜI TỪ KẾT QUẢ BACKTEST 87 MÃ
# ============================================

PROFITABLE_WATCHLIST = [
    # Nhóm lời > 5%
    'VIX', 'PNJ', 'DQC', 'BID', 'VRE', 'DGW',
    
    # Nhóm lời 3-5%
    'SSI', 'MBB', 'DGC', 'CTD', 'PVT',
    
    # Nhóm lời 2-3%
    'LCG', 'YEG', 'TMP', 'FCN', 'VCG', 'SZC', 'IJC',
    
    # Nhóm lời 1-2%
    'TCB', 'BVH', 'TDM', 'DPR', 'BMI', 'NLG', 'VGT', 'TV2', 'VGC', 'GEX', 'VCI', 'FPT', 'GAS',
    
    # Nhóm lời 0-1%
    'GMD', 'DIG', 'HSG', 'PLX', 'OCB', 'BVS', 'DHG', 'VHM', 'TCM', 'TPB', 'CTG', 'MBS', 'VSC'
]

# ============================================
# CẤU HÌNH THỜI GIAN BACKTEST
# ============================================

# Backtest từ 01/06/2026 đến 31/08/2026 (2 tháng)
BACKTEST_START = "2026-06-01"
BACKTEST_END = "2026-08-31"

# ============================================
# HÀM LẤY DỮ LIỆU THỊ TRƯỜNG
# ============================================

def get_market_data_for_period():
    """Lấy dữ liệu VN-Index cho giai đoạn 2 tháng"""
    print("🌐 Đang tải dữ liệu VN-Index H1...")
    
    for src in ["VCI", "TCBS", "KBS"]:
        try:
            quote = Quote(symbol="VNINDEX", source=src)
            df_vni = quote.history(
                start=BACKTEST_START,
                end=BACKTEST_END,
                interval="1H"
            )
            if df_vni is not None and not df_vni.empty:
                df_vni['dt'] = pd.to_datetime(df_vni['time'])
                df_vni = df_vni.sort_values('dt')
                df_vni['VNI_MA20'] = df_vni['close'].rolling(20).mean()
                df_vni['vol_ma20'] = df_vni['volume'].rolling(20).mean()
                print(f"✅ Đã tải VN-Index từ {src} ({len(df_vni)} bars)")
                time.sleep(2)
                return df_vni[['dt', 'close', 'volume', 'VNI_MA20', 'vol_ma20']].rename(
                    columns={'close': 'VNI_Close', 'volume': 'VNI_Volume', 'vol_ma20': 'VNI_Vol_MA20'}
                )
        except Exception as e:
            print(f"  ❌ Lỗi {src}: {str(e)[:50]}")
            continue
    return None

# ============================================
# HÀM BACKTEST 1 MÃ CHO GIAI ĐOẠN CỤ THỂ
# ============================================

def process_symbol_period(symbol, df_vni):
    """Backtest 1 mã cho giai đoạn 2 tháng"""
    trades = []
    try:
        quote = Quote(symbol=symbol, source="KBS")
        df = quote.history(
            start=BACKTEST_START,
            end=BACKTEST_END,
            interval="1H"
        )

        if df is None or df.empty or len(df) < 40:
            return trades

        # Ichimoku
        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2

        # ATR
        df['tr0'] = df['high'] - df['low']
        df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
        df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()

        # Merge market
        df['dt'] = pd.to_datetime(df['time'])
        df = df.sort_values('dt')
        df = pd.merge_asof(df, df_vni, on='dt', direction='backward')

        in_pos = False
        entry_p, entry_t = 0, None
        sl_p, tp_p = 0, 0

        for idx in range(30, len(df)):
            row = df.iloc[idx]
            prev = df.iloc[idx - 1]

            vni_trend_ok = (row['VNI_Close'] > row['VNI_MA20']) if pd.notnull(row['VNI_MA20']) else True
            market_liquidity_ok = (row['VNI_Volume'] >= 0.7 * row['VNI_Vol_MA20']) if pd.notnull(row['VNI_Vol_MA20']) else True

            market_ok = vni_trend_ok and market_liquidity_ok
            cross_up = (prev['tenkan'] <= prev['kijun']) and (row['tenkan'] > row['kijun'])

            if not in_pos:
                if market_ok and cross_up and pd.notnull(row['atr']) and row['atr'] > 0:
                    in_pos = True
                    entry_p = row['close']
                    entry_t = row['time']
                    sl_p = entry_p - (2.0 * row['atr'])
                    tp_p = entry_p + (4.5 * row['atr'])
            else:
                exit_p = None
                reason = ""

                current_profit_dist = row['close'] - entry_p
                if current_profit_dist >= (2.0 * row['atr']):
                    new_sl = row['close'] - (1.5 * row['atr'])
                    if new_sl > sl_p:
                        sl_p = new_sl
                        reason = "Breakeven/Trailing"

                if row['low'] <= sl_p:
                    exit_p = sl_p
                    if not reason:
                        reason = "SL"
                elif row['high'] >= tp_p:
                    exit_p = tp_p
                    reason = "TP ATR (4.5x)"
                elif (row['close'] < row['kijun']) and (prev['close'] < prev['kijun']):
                    exit_p = row['close']
                    reason = "Trailing Kijun"

                if exit_p is not None:
                    net_entry = entry_p * (1 + BUY_FEE)
                    net_exit = exit_p * (1 - SELL_FEE - SELL_TAX)
                    pnl_pct = (net_exit - net_entry) / net_entry

                    trades.append({
                        'Mã': symbol,
                        'Vào lệnh': entry_t,
                        'Thoát lệnh': row['time'],
                        'Giá vào': entry_p,
                        'Giá ra': exit_p,
                        'Lãi/Lỗ (%)': pnl_pct * 100,
                        'Lý do': reason
                    })
                    in_pos = False
        return trades
    except Exception as e:
        return []

# ============================================
# HÀM GỬI THÔNG BÁO TELEGRAM
# ============================================

def send_telegram_message(message):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Chưa cấu hình Token hoặc Chat ID cho Telegram, bỏ qua gửi tin nhắn.")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Đã gửi thông báo Telegram thành công!")
        else:
            print(f"❌ Lỗi gửi Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Lỗi kết nối Telegram: {e}")

# ============================================
# HÀM CHẠY BACKTEST VÀ TỔNG HỢP
# ============================================

def run_backtest_profitable_period():
    """Chạy backtest cho 44 mã có lời trong 2 tháng"""
    df_vni = get_market_data_for_period()
    if df_vni is None:
        print("❌ Không lấy được VN-Index!")
        return

    print(f"\n🚀 CHẠY BACKTEST {len(PROFITABLE_WATCHLIST)} MÃ CÓ LỜI...")
    print(f"📅 Giai đoạn: {BACKTEST_START} đến {BACKTEST_END}")
    print("=" * 60)
    print(f"⏱️  Thời gian dự kiến: {len(PROFITABLE_WATCHLIST) * 3.5 / 60:.1f} phút")
    print("=" * 60)

    all_trades = []
    failed_symbols = []
    start_time = time.time()

    for i, symbol in enumerate(PROFITABLE_WATCHLIST, 1):
        elapsed = time.time() - start_time
        remaining = (len(PROFITABLE_WATCHLIST) - i) * 3.5
        
        print(f"\r📡 [{i}/{len(PROFITABLE_WATCHLIST)}] {symbol} | "
              f"Đã chạy: {elapsed/60:.1f}ph | Còn lại: ~{remaining/60:.1f}ph", end="")
        
        trades = process_symbol_period(symbol, df_vni)
        if trades:
            all_trades.extend(trades)
            total_pnl = sum(t['Lãi/Lỗ (%)'] for t in trades)
            print(f"\n  {'✅' if total_pnl > 0 else '❌'} {symbol}: {total_pnl:+.2f}% ({len(trades)} lệnh)")
        else:
            failed_symbols.append(symbol)
        
        time.sleep(3.5)

    print(f"\n\n✅ Hoàn tất trong {(time.time() - start_time)/60:.1f} phút!")
    
    analyze_results(all_trades, failed_symbols)

def analyze_results(all_trades, failed_symbols):
    """Phân tích kết quả và gửi Telegram"""
    if not all_trades:
        print("❌ Không có lệnh nào!")
        return

    df_res = pd.DataFrame(all_trades)
    
    # Portfolio simulation
    initial_nav = 1_000_000_000
    current_nav = initial_nav
    peak_nav = initial_nav
    max_drawdown = 0

    df_res['Thoát lệnh'] = pd.to_datetime(df_res['Thoát lệnh'])
    df_res = df_res.sort_values('Thoát lệnh').reset_index(drop=True)

    for idx, row in df_res.iterrows():
        trade_result_pct = row['Lãi/Lỗ (%)'] / 100
        allocated_capital = current_nav * 0.10
        pnl_amount = allocated_capital * trade_result_pct
        current_nav += pnl_amount

        if current_nav > peak_nav:
            peak_nav = current_nav
        drawdown = (current_nav - peak_nav) / peak_nav
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    total_return_pct = ((current_nav - initial_nav) / initial_nav) * 100
    win_rate = (df_res['Lãi/Lỗ (%)'] > 0).sum() / len(df_res) * 100

    print("\n" + "=" * 80)
    print(f"💰 BÁO CÁO HIỆU SUẤT - CHỈ MÃ CÓ LỜI ({BACKTEST_START} đến {BACKTEST_END})")
    print("=" * 80)
    print(f"• Vốn ban đầu (Initial NAV)     : {initial_nav:,.0f} VNĐ")
    print(f"• Tổng tài sản cuối kỳ (NAV)   : {current_nav:,.0f} VNĐ")
    print(f"• Tổng suất sinh lợi (RoR)     : {total_return_pct:+.2f}%")
    print(f"• Tổng số lệnh khớp            : {len(df_res)}")
    print(f"• Tỷ lệ thắng (Winrate)        : {win_rate:.1f}%")
    print(f"• Max Drawdown                 : {max_drawdown*100:.2f}%")
    print("=" * 80)

    # Bảng xếp hạng
    print("\n📊 BẢNG XẾP HẠNG CHI TIẾT:")
    symbol_summary = df_res.groupby('Mã').agg(
        Số_lệnh=('Lãi/Lỗ (%)', 'count'),
        Thắng=('Lãi/Lỗ (%)', lambda x: (x > 0).sum()),
        Thua=('Lãi/Lỗ (%)', lambda x: (x <= 0).sum()),
        Winrate=('Lãi/Lỗ (%)', lambda x: f"{(x > 0).sum()/len(x)*100:.1f}%"),
        Tổng_PnL_pct=('Lãi/Lỗ (%)', 'sum')
    ).sort_values(by='Tổng_PnL_pct', ascending=False)
    
    print(tabulate(symbol_summary, headers='keys', tablefmt='grid', showindex=True))

    # Thống kê
    profitable = symbol_summary[symbol_summary['Tổng_PnL_pct'] > 0]
    losing = symbol_summary[symbol_summary['Tổng_PnL_pct'] <= 0]
    
    print("\n📈 THỐNG KÊ NHÓM:")
    print(f"  • Số mã có lời: {len(profitable)} ({len(profitable)/len(symbol_summary)*100:.1f}%)")
    print(f"  • Số mã bị lỗ: {len(losing)} ({len(losing)/len(symbol_summary)*100:.1f}%)")
    print(f"  • Số mã không có lệnh: {len(failed_symbols)}")
    
    # Chuẩn bị và gửi tin nhắn Telegram
    top_3_str = ""
    for i, (sym, r) in enumerate(profitable.head(3).iterrows(), 1):
        top_3_str += f"  {i}. {sym}: +{r['Tổng_PnL_pct']:.2f}%\n"

    telegram_msg = f"""<b>🚀 BÁO CÁO BACKTEST 44 MÃ</b>
📅 Giai đoạn: {BACKTEST_START} đến {BACKTEST_END}

💰 <b>Tổng RoR:</b> {total_return_pct:+.2f}%
🎯 <b>Winrate:</b> {win_rate:.1f}%
📉 <b>Max Drawdown:</b> {max_drawdown*100:.2f}%
✅ <b>Số mã có lời:</b> {len(profitable)} mã
❌ <b>Số mã lỗ:</b> {len(losing)} mã

🏆 <b>Top 3 Mã Tốt Nhất:</b>
{top_3_str}
"""
    send_telegram_message(telegram_msg)

# ============================================
# KHỞI CHẠY CHƯƠNG TRÌNH
# ============================================

if __name__ == "__main__":
    print("=" * 80)
    print("🚀 BACKTEST CHỈ MÃ CÓ LỜI - GIAI ĐOẠN 2 THÁNG")
    print("=" * 80)
    print(f"📊 Tổng số mã: {len(PROFITABLE_WATCHLIST)}")
    print(f"📅 Giai đoạn: {BACKTEST_START} đến {BACKTEST_END}")
    print("=" * 80)
    
    run_backtest_profitable_period()
 
