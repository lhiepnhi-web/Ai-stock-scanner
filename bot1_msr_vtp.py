import os
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

from vnstock import Quote


# ============================================================
# 1. DANH SÁCH CỔ PHIẾU
# ============================================================

TICKERS = [
    "MSR",
    "VGI",
    "ACB",
    "NVL",
    "BSR",
    "GEX",
    "VPB",
    "PNJ",
    "SHS",
    "SHB",
    "CII",
    "DPM",
    "DGW",
    "SAB",
    "BMP",
    "DHA",
    "VGC",
    "LPB",
    "PAN",
    "VCB",
    "TVS",
    "VND",
    "NKG",
    "HDB",
    "DCM",
    "ABB",
    "NAB",
    "CTD",
    "C69",
    "VIC",
    "VJC",
    "PVI",
    "PLC",
    "MSB",
    "KSV",
    "NVB",
    "PVC",
    "THD",
    "SZL",
    "BAF",
    "NAF",
    "DCL",
    "BFC",
    "ELC",
    "HCD",
    "NKV",
]


# ============================================================
# 2. CẤU HÌNH
# ============================================================

SOURCE = "KBS"

# Lấy đủ dữ liệu lịch sử để tính indicator
START_DATE = "2017-01-01"

# Ngày hiện tại
END_DATE = datetime.now().strftime("%Y-%m-%d")

MAX_HOLD = 10
TAKE_PROFIT = 0.20

# File lưu trạng thái vị thế
STATE_FILE = "positions.json"

# File lưu lịch sử tín hiệu
SIGNAL_FILE = "signals_history.csv"


# ============================================================
# 3. KIỂM TRA KHUNG GIỜ GIAO DỊCH (VIỆT NAM)
# ============================================================

def is_trading_time():
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vn_tz)
    
    # Kiểm tra thứ trong tuần (5 = Thứ 7, 6 = Chủ Nhật)
    if now.weekday() >= 5:
        print('💤 Ngoài khung giờ giao dịch chứng khoán Việt Nam.')
        return False
        
    current_time = now.time()
    
    # Khung giờ giao dịch chuẩn: Sáng 09:00 - 11:30, Chiều 13:00 - 14:30
    morning_start = datetime.strptime("09:00", "%H:%M").time()
    morning_end = datetime.strptime("11:30", "%H:%M").time()
    
    afternoon_start = datetime.strptime("13:00", "%H:%M").time()
    afternoon_end = datetime.strptime("14:30", "%H:%M").time()
    
    is_morning = morning_start <= current_time <= morning_end
    is_afternoon = afternoon_start <= current_time <= afternoon_end
    
    if is_morning or is_afternoon:
        return True
        
    print('💤 Ngoài khung giờ giao dịch chứng khoán Việt Nam.')
    return False


# ============================================================
# 4. TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(
            url,
            data=data,
            timeout=20
        )
    except Exception as e:
        print("Telegram lỗi:", e)


# ============================================================
# 5. LOAD STATE
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:
        return {}


# ============================================================
# 6. SAVE STATE
# ============================================================

def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# 7. LOAD DATA
# ============================================================

def load_data(ticker):

    try:

        quote = Quote(
            symbol=ticker,
            source=SOURCE
        )

        df = quote.history(
            start=START_DATE,
            end=END_DATE,
            interval="1D"
        )

        if df is None or len(df) == 0:
            return None

        df = df.copy()

        df.columns = [
            str(c).strip().lower()
            for c in df.columns
        ]

        if "time" in df.columns:

            df["date"] = pd.to_datetime(
                df["time"]
            )

        elif "date" in df.columns:

            df["date"] = pd.to_datetime(
                df["date"]
            )

        else:

            return None

        rename = {}

        for c in df.columns:

            if c in ["open"]:
                rename[c] = "open"

            elif c in ["high"]:
                rename[c] = "high"

            elif c in ["low"]:
                rename[c] = "low"

            elif c in ["close"]:
                rename[c] = "close"

            elif c in ["volume"]:
                rename[c] = "volume"

        df = df.rename(
            columns=rename
        )

        required = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        if not all(
            c in df.columns
            for c in required
        ):
            return None

        df = df[
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        ].copy()

        df = df.dropna()

        df = df.sort_values(
            "date"
        )

        df = df.drop_duplicates(
            "date"
        )

        return df.reset_index(drop=True)

    except Exception as e:

        print(
            f"{ticker}: lỗi tải dữ liệu -> {e}"
        )

        return None


# ============================================================
# 8. INDICATORS - Y NGUYÊN V1.0
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    # MACD
    ema12 = (
        df["close"]
        .ewm(
            span=12,
            adjust=False
        )
        .mean()
    )

    ema26 = (
        df["close"]
        .ewm(
            span=26,
            adjust=False
        )
        .mean()
    )

    macd = ema12 - ema26

    signal = (
        macd
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["macd_hist"] = (
        macd - signal
    )

    # ROC10
    df["roc10"] = (
        df["close"]
        / df["close"].shift(10)
        - 1
    ) * 100

    # VOLUME RATIO
    df["vol_ma20"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"]
        / df["vol_ma20"]
    )

    # ADX14
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where(
        (plus_dm > minus_dm) &
        (plus_dm > 0),
        0
    )

    minus_dm = minus_dm.where(
        (minus_dm > plus_dm) &
        (minus_dm > 0),
        0
    )

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr14 = (
        tr
        .rolling(14)
        .mean()
    )

    plus_di = (
        100 *
        plus_dm
        .rolling(14)
        .mean()
        / atr14
    )

    minus_di = (
        100 *
        minus_dm
        .rolling(14)
        .mean()
        / atr14
    )

    denominator = (
        plus_di +
        minus_di
    )

    dx = (
        (
            plus_di -
            minus_di
        ).abs()
        / denominator
    ) * 100

    df["adx"] = (
        dx
        .rolling(14)
        .mean()
    )

    return df


# ============================================================
# 9. KIỂM TRA LUẬT V1.0
# ============================================================

def check_entry(row):

    volume_ok = (
        row["volume_ratio"] > 1
    )

    macd_ok = (
        row["macd_hist"] > 0
    )

    roc_ok = (
        row["roc10"] > 2
    )

    adx_ok = (
        row["adx"] > 30
    )

    return (
        volume_ok and
        macd_ok and
        roc_ok and
        adx_ok
    )


# ============================================================
# 10. QUÉT MỘT MÃ
# ============================================================

def scan_ticker(
    ticker,
    state
):

    df = load_data(ticker)

    if df is None:

        return {
            "ticker": ticker,
            "status": "DATA_ERROR"
        }

    df = calculate_indicators(df)

    if len(df) < 50:

        return {
            "ticker": ticker,
            "status": "NOT_ENOUGH_DATA"
        }

    row = df.iloc[-1]

    date = row["date"]
    close = float(row["close"])
    high = float(row["high"])
    volume_ratio = float(row["volume_ratio"])
    macd_hist = float(row["macd_hist"])
    roc10 = float(row["roc10"])
    adx = float(row["adx"])

    entry_ok = check_entry(row)

    position = state.get(ticker)
    action = "HOLD / NO SIGNAL"
    reason = ""

    if position:

        entry_price = float(
            position["entry_price"]
        )

        entry_date = pd.to_datetime(
            position["entry_date"]
        )

        hold = (
            pd.Timestamp(date)
            - entry_date
        ).days

        entry_idx_list = df.index[
            df["date"] >= entry_date
        ]

        if len(entry_idx_list) > 0:

            entry_idx = (
                entry_idx_list[0]
            )

            hold_sessions = (
                len(df) -
                1 -
                entry_idx
            )

        else:

            hold_sessions = hold

        tp_price = (
            entry_price *
            (1 + TAKE_PROFIT)
        )

        if high >= tp_price:

            action = "🔴 THOÁT"
            reason = "ĐẠT TAKE PROFIT +20%"
            state.pop(ticker, None)

        elif not entry_ok:

            action = "🔴 THOÁT"
            reason = "MẤT LUẬT V1.0"
            state.pop(ticker, None)

        elif hold_sessions >= MAX_HOLD:

            action = "🔴 THOÁT"
            reason = "ĐỦ 10 PHIÊN"
            state.pop(ticker, None)

        else:

            action = "🟢 GIỮ"
            reason = f"Đang giữ - {hold_sessions} phiên"

    else:

        if entry_ok:

            action = "🟢 MUA"
            reason = "ĐỦ 4 ĐIỀU KIỆN V1.0"

            state[ticker] = {
                "entry_date": str(date.date()),
                "entry_price": close
            }

        else:

            action = "⚪ KHÔNG TÍN HIỆU"
            reason = "Chưa đủ 4 điều kiện"

    return {
        "ticker": ticker,
        "date": str(date.date()),
        "action": action,
        "reason": reason,
        "close": round(close, 2),
        "volume_ratio": round(volume_ratio, 2),
        "macd_hist": round(macd_hist, 4),
        "roc10": round(roc10, 2),
        "adx": round(adx, 2)
    }


# ============================================================
# 11. MAIN
# ============================================================

def main():
    # Kiểm tra khung giờ giao dịch trước khi chạy
    if not is_trading_time():
        return

    print()
    print("=" * 80)
    print("V1.0 SIGNAL BOT")
    print("=" * 80)

    print(
        "Ngày:",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print(
        "Số mã:",
        len(TICKERS)
    )

    print("=" * 80)

    state = load_state()
    results = []

    for ticker in TICKERS:

        print(f"Đang quét: {ticker}")

        result = scan_ticker(
            ticker,
            state
        )

        results.append(result)

        if result.get("status") == "DATA_ERROR":
            print("  ❌ Không có dữ liệu")
        elif result.get("status") == "NOT_ENOUGH_DATA":
            print("  ⚪ Không đủ dữ liệu")
        else:
            print(f"  {result['action']} | {result['reason']}")

        time.sleep(0.5)

    save_state(state)

    history = pd.DataFrame(results)
    history["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if os.path.exists(SIGNAL_FILE):
        history.to_csv(
            SIGNAL_FILE,
            mode="a",
            header=False,
            index=False
        )
    else:
        history.to_csv(
            SIGNAL_FILE,
            index=False
        )

    buy_signals = [x for x in results if x.get("action") == "🟢 MUA"]
    sell_signals = [x for x in results if x.get("action") == "🔴 THOÁT"]
    hold_signals = [x for x in results if x.get("action") == "🟢 GIỮ"]

    message = []
    message.append("📊 V1.0 SIGNAL BOT")
    message.append(datetime.now().strftime("%d/%m/%Y %H:%M"))
    message.append("")

    if buy_signals:
        message.append("🟢 TÍN HIỆU MUA")
        for x in buy_signals:
            message.append(
                f"{x['ticker']} | Giá {x['close']} | "
                f"VR {x['volume_ratio']} | ROC {x['roc10']} | ADX {x['adx']}"
            )

    if sell_signals:
        message.append("")
        message.append("🔴 TÍN HIỆU THOÁT")
        for x in sell_signals:
            message.append(
                f"{x['ticker']} | {x['reason']} | Giá {x['close']}"
            )

    if hold_signals:
        message.append("")
        message.append("🟢 ĐANG GIỮ")
        for x in hold_signals:
            message.append(
                f"{x['ticker']} | Giá {x['close']} | {x['reason']}"
            )

    message.append("")
    message.append(f"Tổng mã: {len(TICKERS)}")
    message.append(f"Mua: {len(buy_signals)}")
    message.append(f"Thoát: {len(sell_signals)}")
    message.append(f"Giữ: {len(hold_signals)}")

    final_message = "\n".join(message)

    print()
    print("=" * 80)
    print(final_message)
    print("=" * 80)

    if buy_signals or sell_signals:
        send_telegram(final_message)

    print()
    print("✅ V1.0 SIGNAL BOT HOÀN TẤT")


if __name__ == "__main__":
    main()
 
