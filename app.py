
import streamlit as st
import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime, timedelta

try:
    from vnstock import Quote
except Exception:
    Quote = None


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Stock Scanner 5M",
    page_icon="📈",
    layout="wide"
)

st.title("🚀 AI STOCK SCANNER — KHUNG 5 PHÚT")
st.caption("69 mã thanh khoản tốt | Rate-limit safe | Cache | Progress")


SYMBOLS = [
    "SHB", "HPG", "FPT", "VIX", "SSI", "VIC", "VPB", "MWG",
    "STB", "MSN", "MBB", "TCB", "VCB", "HDB", "CII", "VHM",
    "CTG", "GEX", "VND", "ACB", "VNM", "VRE", "CEO", "VCI",
    "BID", "PDR", "NVL", "HCM", "TPB", "PVS", "DIG", "DGC",
    "EIB", "GAS", "POW", "VCG", "KDH", "KBC", "HAG", "MSB",
    "GMD", "VPI", "DPM", "DCM", "PC1", "MBS", "PNJ", "PVD",
    "LPB", "NKG", "DBC", "DGW", "IDC", "HHV", "BAF", "VHC",
    "HSG", "SAB", "VGC", "ANV", "FTS", "CTR", "REE", "SSB",
    "OCB", "LCG", "BSI", "NAB", "SBT"
]

# Guest limit hiện tại = 20 request/phút.
# Chừa 2 request/phút làm biên an toàn.
MAX_REQUESTS_PER_MINUTE = 18

# Cache 5 phút.
CACHE_TTL_SECONDS = 300

# Dữ liệu cần tối thiểu.
MIN_ROWS = 30


# ============================================================
# SESSION STATE
# ============================================================

if "data_cache" not in st.session_state:
    st.session_state.data_cache = {}

if "last_scan" not in st.session_state:
    st.session_state.last_scan = None

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:

    def __init__(self, max_requests=18, period=60):
        self.max_requests = max_requests
        self.period = period
        self.timestamps = []
        self.lock = threading.Lock()

    def wait(self, progress_callback=None):

        while True:

            with self.lock:

                now = time.time()

                self.timestamps = [
                    t for t in self.timestamps
                    if now - t < self.period
                ]

                if len(self.timestamps) < self.max_requests:
                    self.timestamps.append(now)
                    return

                wait_seconds = (
                    self.period -
                    (now - self.timestamps[0]) +
                    0.5
                )

            wait_seconds = max(1, wait_seconds)

            if progress_callback:
                progress_callback(
                    f"⏳ API giới hạn — chờ {wait_seconds:.0f}s..."
                )

            time.sleep(min(wait_seconds, 5))


rate_limiter = RateLimiter(
    MAX_REQUESTS_PER_MINUTE,
    60
)


# ============================================================
# DATA NORMALIZATION
# ============================================================

def normalize_dataframe(df):

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):

        try:
            df = pd.DataFrame(df)
        except Exception:
            return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Xử lý MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):

        new_cols = []

        for c in df.columns:

            if isinstance(c, tuple):
                new_cols.append(
                    str(c[0]).lower().strip()
                )
            else:
                new_cols.append(
                    str(c).lower().strip()
                )

        df.columns = new_cols

    else:

        df.columns = [
            str(c).lower().strip()
            for c in df.columns
        ]

    aliases = {
        "date": "time",
        "datetime": "time",
        "tradingdate": "time",
        "vol": "volume",
        "adj close": "close",
        "adjusted close": "close"
    }

    df = df.rename(
        columns={
            c: aliases.get(c, c)
            for c in df.columns
        }
    )

    # Nếu time nằm ở index
    if "time" not in df.columns:

        if isinstance(
            df.index,
            pd.DatetimeIndex
        ):

            df = df.reset_index()

            first_col = df.columns[0]

            df = df.rename(
                columns={
                    first_col: "time"
                }
            )

    required = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]

    for col in required:

        if col not in df.columns:
            return pd.DataFrame()

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    if "time" in df.columns:

        df["time"] = pd.to_datetime(
            df["time"],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    )

    if "time" in df.columns:

        df = (
            df
            .sort_values("time")
            .drop_duplicates("time")
            .reset_index(drop=True)
        )

    return df


# ============================================================
# CACHE
# ============================================================

def get_cached(symbol):

    item = st.session_state.data_cache.get(symbol)

    if not item:
        return None

    timestamp = item["timestamp"]

    if time.time() - timestamp > CACHE_TTL_SECONDS:
        return None

    return item["data"].copy()


def save_cache(symbol, df):

    st.session_state.data_cache[symbol] = {
        "timestamp": time.time(),
        "data": df.copy()
    }


def clear_cache():

    st.session_state.data_cache = {}


# ============================================================
# FETCH DATA
# ============================================================

def fetch_symbol(symbol, status_callback=None):

    cached = get_cached(symbol)

    if cached is not None:
        return cached, "CACHE"

    if Quote is None:
        return pd.DataFrame(), "vnstock chưa cài"

    try:

        if status_callback:
            status_callback(
                f"📡 Đang tải {symbol}..."
            )

        rate_limiter.wait(
            status_callback
        )

        quote = Quote(
            symbol=symbol,
            source="KBS"
        )

        # Lấy lịch sử đủ để tính TB20.
        # KBS có thể trả nhiều hơn mức cần thiết.
        df = quote.history(
            start=(
                datetime.now()
                - timedelta(days=45)
            ).strftime("%Y-%m-%d"),
            end=(
                datetime.now()
                + timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            interval="5m"
        )

        df = normalize_dataframe(df)

        if df.empty:
            return pd.DataFrame(), "NO DATA"

        if len(df) < MIN_ROWS:
            return df, f"Ít dữ liệu ({len(df)})"

        save_cache(symbol, df)

        return df, "OK"

    except Exception as e:

        msg = str(e)

        # Không in cả traceback dài lên giao diện
        if "rate" in msg.lower():
            status = "RATE LIMIT"
        elif "timeout" in msg.lower():
            status = "TIMEOUT"
        elif "429" in msg:
            status = "HTTP 429"
        else:
            status = "ERROR"

        return pd.DataFrame(), status


# ============================================================
# INDICATORS
# ============================================================

def calculate_signal(symbol, df):

    if df is None or df.empty:
        return None

    df = df.copy()

    if len(df) < 20:
        return None

    df["vol_ma20"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["volume_ratio"] = (
        df["volume"] /
        df["vol_ma20"].replace(0, np.nan)
    )

    df["ema9"] = (
        df["close"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["ema20"] = (
        df["close"]
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    df["high20"] = (
        df["high"]
        .rolling(20)
        .max()
        .shift(1)
    )

    df["low20"] = (
        df["low"]
        .rolling(20)
        .min()
        .shift(1)
    )

    latest = df.iloc[-1]

    close = float(latest["close"])
    volume_ratio = float(
        latest["volume_ratio"]
    )

    ema9 = float(latest["ema9"])
    ema20 = float(latest["ema20"])

    high20 = latest["high20"]

    score = 0
    reasons = []

    # Volume
    if volume_ratio >= 2.0:
        score += 35
        reasons.append("Volume x2")
    elif volume_ratio >= 1.5:
        score += 25
        reasons.append("Volume tăng mạnh")
    elif volume_ratio >= 1.2:
        score += 15
        reasons.append("Volume tăng")

    # Trend
    if close > ema20:
        score += 20
        reasons.append("Trên EMA20")

    if ema9 > ema20:
        score += 15
        reasons.append("EMA9 > EMA20")

    # Breakout
    if pd.notna(high20) and close > float(high20):
        score += 25
        reasons.append("Breakout 20")

    # Action
    if score >= 75:
        action = "🔥 BUY"
    elif score >= 55:
        action = "👀 WATCH"
    else:
        action = "—"

    return {
        "Mã": symbol,
        "Giá": round(close, 2),
        "Volume/TB20": round(
            volume_ratio, 2
        ) if np.isfinite(volume_ratio) else 0,
        "Score": int(score),
        "Tín hiệu": action,
        "Lý do": ", ".join(reasons)
    }


# ============================================================
# SCAN
# ============================================================

def run_scan(symbols, force_refresh=False):

    if force_refresh:
        clear_cache()

    total = len(symbols)

    results = []
    errors = []

    progress = st.progress(
        0,
        text=f"🚀 Chuẩn bị quét {total} mã..."
    )

    status = st.empty()

    start_time = time.time()

    cache_hits = 0

    for i, symbol in enumerate(symbols, 1):

        def update_status(message):
            status.info(
                f"{message}  |  {i}/{total}"
            )

        df, state = fetch_symbol(
            symbol,
            update_status
        )

        if state == "CACHE":
            cache_hits += 1

        if df.empty:

            errors.append({
                "Mã": symbol,
                "Lỗi": state
            })

        else:

            result = calculate_signal(
                symbol,
                df
            )

            if result:
                results.append(result)

        elapsed = time.time() - start_time

        progress.progress(
            i / total,
            text=(
                f"📊 Đang quét {i}/{total} "
                f"| OK: {len(results)} "
                f"| Lỗi: {len(errors)} "
                f"| Cache: {cache_hits} "
                f"| {elapsed:.0f}s"
            )
        )

    progress.progress(
        1.0,
        text=(
            f"✅ Hoàn tất {total}/{total} mã"
        )
    )

    status.success(
        f"Quét xong trong {time.time() - start_time:.1f}s"
    )

    result_df = pd.DataFrame(results)

    if not result_df.empty:

        result_df = (
            result_df
            .sort_values(
                ["Score", "Volume/TB20"],
                ascending=False
            )
            .reset_index(drop=True)
        )

    error_df = pd.DataFrame(errors)

    return result_df, error_df, cache_hits


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Cấu hình")

selected = st.sidebar.multiselect(
    "Mã theo dõi",
    SYMBOLS,
    default=SYMBOLS
)

st.sidebar.divider()

st.sidebar.metric(
    "Tổng mã",
    len(SYMBOLS)
)

st.sidebar.metric(
    "Đang chọn",
    len(selected)
)

st.sidebar.caption(
    "API limit: 20 request/phút"
)

st.sidebar.caption(
    "Scanner dùng tối đa 18 request/phút"
)

st.sidebar.caption(
    "Cache dữ liệu: 5 phút"
)


# ============================================================
# BUTTONS
# ============================================================

col1, col2 = st.columns(2)

with col1:

    scan_now = st.button(
        "🔎 QUÉT NGAY",
        type="primary",
        use_container_width=True
    )

with col2:

    force_scan = st.button(
        "♻️ XÓA CACHE & QUÉT LẠI",
        use_container_width=True
    )


# ============================================================
# SCAN ACTION
# ============================================================

if scan_now or force_scan:

    if not selected:

        st.warning(
            "⚠️ Chưa chọn mã nào."
        )

    else:

        result_df, error_df, cache_hits = run_scan(
            selected,
            force_refresh=force_scan
        )

        st.session_state.scan_results = result_df
        st.session_state.last_scan = datetime.now()


# ============================================================
# DISPLAY
# ============================================================

if st.session_state.scan_results is not None:

    result_df = st.session_state.scan_results

    st.subheader("🎯 KẾT QUẢ SCANNER")

    if st.session_state.last_scan:

        st.caption(
            "Lần quét: "
            + st.session_state.last_scan.strftime(
                "%d/%m/%Y %H:%M:%S"
            )
        )

    if result_df.empty:

        st.warning(
            "Không có mã nào đủ điều kiện."
        )

    else:

        buy_df = result_df[
            result_df["Tín hiệu"] == "🔥 BUY"
        ]

        watch_df = result_df[
            result_df["Tín hiệu"] == "👀 WATCH"
        ]

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "🔥 BUY",
            len(buy_df)
        )

        c2.metric(
            "👀 WATCH",
            len(watch_df)
        )

        c3.metric(
            "Tổng có dữ liệu",
            len(result_df)
        )

        st.dataframe(
            result_df,
            use_container_width=True,
            hide_index=True
        )

else:

    st.info(
        "👆 Bấm **QUÉT NGAY** để bắt đầu."
    )
