import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from vnstock import Quote
import requests
import warnings
warnings.filterwarnings('ignore')

# Nếu bạn để các biến cấu hình trong config.py thì import vào, 
# hoặc bạn có thể khai báo trực tiếp các hằng số vào đây luôn cho gọn:
from config import * 

class TradingBot:
    """Bot giao dịch tự động cho thị trường Việt Nam"""
    
    def __init__(self):
        self.positions = {}  
        self.trades_history = []  
        self.current_capital = INITIAL_CAPITAL
        self.peak_capital = INITIAL_CAPITAL
        self.max_drawdown = 0
        self.df_vni = None
        self.last_scan_time = None
        
    def is_trading_hours(self) -> bool:
        """Kiểm tra có đang trong giờ giao dịch không"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        if now.weekday() >= 5:  
            return False
        
        if MORNING_START <= current_time <= MORNING_END:
            return True
        
        if AFTERNOON_START <= current_time <= AFTERNOON_END:
            return True
        
        return False
    
    def get_market_data(self) -> Optional[pd.DataFrame]:
        for src in ["VCI", "TCBS", "KBS"]:
            try:
                quote = Quote(symbol="VNINDEX", source=src)
                df_vni = quote.history(
                    start=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                    end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval="1H"
                )
                if df_vni is not None and not df_vni.empty:
                    df_vni['dt'] = pd.to_datetime(df_vni['time'])
                    df_vni = df_vni.sort_values('dt')
                    df_vni['VNI_MA20'] = df_vni['close'].rolling(20).mean()
                    df_vni['vol_ma20'] = df_vni['volume'].rolling(20).mean()
                    return df_vni[['dt', 'close', 'volume', 'VNI_MA20', 'vol_ma20']].rename(
                        columns={'close': 'VNI_Close', 'volume': 'VNI_Volume', 'vol_ma20': 'VNI_Vol_MA20'}
                    )
            except Exception as e:
                continue
            time.sleep(2)
        return None
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
        
        df['tr0'] = df['high'] - df['low']
        df['tr1'] = (df['high'] - df['close'].shift(1)).abs()
        df['tr2'] = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()
        return df
    
    def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        try:
            quote = Quote(symbol=symbol, source="KBS")
            df = quote.history(
                start=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                end=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval="1H"
            )
            if df is None or df.empty or len(df) < 60:
                return None
            
            df = self.calculate_indicators(df)
            df['dt'] = pd.to_datetime(df['time'])
            df = df.sort_values('dt')
            
            if self.df_vni is not None:
                df = pd.merge_asof(df, self.df_vni, on='dt', direction='backward')
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            vni_ok = (latest['VNI_Close'] > latest['VNI_MA20']) if pd.notnull(latest.get('VNI_MA20')) else True
            cross_up = (prev['tenkan'] <= prev['kijun']) and (latest['tenkan'] > latest['kijun'])
            
            if vni_ok and cross_up and pd.notnull(latest['atr']) and latest['atr'] > 0:
                entry_price = latest['close']
                sl = entry_price - (SL_MULTIPLIER * latest['atr'])
                tp = entry_price + (TP_MULTIPLIER * latest['atr'])
                
                return {
                    'symbol': symbol,
                    'signal': 'BUY',
                    'entry_price': entry_price,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'atr': latest['atr'],
                    'time': str(latest['time']),
                    'current_price': latest['close']
                }
            return None
        except Exception as e:
            return None
    
    def scan_all_symbols(self) -> List[Dict]:
        signals = []
        for symbol in WATCHLIST:
            if symbol in self.positions:
                continue
            if len(self.positions) >= MAX_CONCURRENT_POSITIONS:
                break
            signal = self.analyze_symbol(symbol)
            if signal:
                signals.append(signal)
            time.sleep(RATE_LIMIT_DELAY)
        return signals
    
    def run_once(self) -> Dict:
        if not self.is_trading_hours():
            return {'status': 'outside_trading_hours'}
        
        self.df_vni = self.get_market_data()
        if self.df_vni is None:
            return {'status': 'no_market_data'}
        
        buy_signals = self.scan_all_symbols()
        
        return {
            'status': 'success',
            'buy_signals': buy_signals,
            'scan_time': datetime.now()
        }

def send_telegram_message(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception:
        pass

if __name__ == "__main__":
    bot = TradingBot()
    result = bot.run_once()
    
    if result['status'] == 'success':
        signals = result['buy_signals']
        if signals:
            msg = "🔥 <b>PHÁT HIỆN TÍN HIỆU MUA TỪ BOT OOP</b> 🔥\n\n"
            for sig in signals:
                msg += f"• Mã: <b>{sig['symbol']}</b>\n"
                msg += f"  - Giá mua: {sig['entry_price']:,.1f}\n"
                msg += f"  - Stop Loss: {sig['stop_loss']:,.1f}\n"
                msg += f"  - Take Profit: {sig['take_profit']:,.1f}\n\n"
            send_telegram_message(msg)
        else:
            print("Quét xong, hiện không có mã nào thỏa mãn.")
    else:
        print(f"Trạng thái quét: {result['status']}")
import os
import requests

def send_telegram_message(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Thiếu Token hoặc Chat ID Telegram!")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Đã gửi tin nhắn Telegram thành công!")
    else:
        print(f"Lỗi gửi tin nhắn: {response.text}")

# Thêm dòng này vào cuối chương trình của bạn sau khi quét xong:
send_telegram_message("🤖 Xin chào! Bot Ichimoku đã quét xong và hệ thống hoạt động bình thường.")
