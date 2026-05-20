from claudedev_shared import ubs_live_price_holdings, ubs_401k_holdings
import yfinance as yf
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor


SPLIT_THRESHOLD = 0.35  # if last/close ratio < this, assume a stock split


def _detect_split_ratio(last_price, last_close):
    """If last_price/last_close suggests a split, return the integer ratio (e.g. 6).
    Returns 1 if no split detected."""
    ratio = last_price / last_close
    if ratio >= SPLIT_THRESHOLD:
        return 1
    inverse = round(1 / ratio)
    if inverse >= 2:
        return inverse
    return 1


def get_price_data(ticker):
    for attempt in range(2):
        try:
            data = yf.Ticker(ticker).fast_info
            last_price = data.last_price
            last_close = data.regular_market_previous_close
            split_ratio = _detect_split_ratio(last_price, last_close)
            if split_ratio > 1:
                last_close = last_close / split_ratio
                print(f"Note: detected {split_ratio}:1 split for {ticker}, "
                      f"adjusted close to ${last_close:.2f}")
            pct_move = (last_price - last_close) / last_close
            return last_price, last_close, pct_move
        except Exception as e:
            if attempt == 0:
                time.sleep(0.5)
            else:
                print(f"Warning: failed to get price for {ticker}: {e}")
    return None, None, None


ETF_DRAWDOWN_TICKERS = ("SPY", "QQQ", "IWM", "EEM")

# Cached 6W/ATH highs per ticker. Highs only refresh once per calendar day;
# `last_price` is still fetched on every call so the drawdown stays current.
# If `last_price` exceeds the cached high intraday, the cache is bumped up so
# we never report a positive drawdown.
_etf_high_cache = {}  # {ticker: {"6W": float|None, "ATH": float|None, "as_of": date}}


def _fetch_etf_highs(ticker):
    t = yf.Ticker(ticker)
    six_weeks_ago = (pd.Timestamp.today() - pd.Timedelta(weeks=6)).strftime("%Y-%m-%d")
    hist_6w = t.history(start=six_weeks_ago, auto_adjust=False)
    hist_max = t.history(period="max", auto_adjust=False)
    return {
        "6W": float(hist_6w["High"].max()) if not hist_6w.empty else None,
        "ATH": float(hist_max["High"].max()) if not hist_max.empty else None,
    }


def _fetch_etf_drawdown(ticker):
    try:
        last_price = yf.Ticker(ticker).fast_info.last_price
        today = pd.Timestamp.today().date()
        cached = _etf_high_cache.get(ticker)
        if cached is None or cached["as_of"] != today:
            highs = _fetch_etf_highs(ticker)
            cached = {**highs, "as_of": today}
            _etf_high_cache[ticker] = cached

        high_6w = cached["6W"]
        high_ath = cached["ATH"]
        if high_6w is not None and last_price > high_6w:
            cached["6W"] = high_6w = last_price
        if high_ath is not None and last_price > high_ath:
            cached["ATH"] = high_ath = last_price

        return {
            "6W": (last_price - high_6w) / high_6w if high_6w else None,
            "ATH": (last_price - high_ath) / high_ath if high_ath else None,
        }
    except Exception as e:
        print(f"Warning: ETF drawdown fetch failed for {ticker}: {e}")
        return {"6W": None, "ATH": None}


def get_etf_drawdowns():
    """Return % drawdown of SPY/QQQ/IWM/EEM from 6-week and all-time highs.

    Result: {ticker: {"6W": decimal_or_None, "ATH": decimal_or_None}}
    """
    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(zip(
            ETF_DRAWDOWN_TICKERS,
            ex.map(_fetch_etf_drawdown, ETF_DRAWDOWN_TICKERS)))


INTRADAY_TICKERS = ("SPY", "QQQ", "IWM")


def _fetch_intraday(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m", prepost=False)
        prev_close = None
        try:
            prev_close = float(t.fast_info.regular_market_previous_close)
        except Exception:
            pass
        if hist is None or hist.empty:
            return {"hist": None, "prev_close": prev_close}
        return {"hist": hist[["Close"]], "prev_close": prev_close}
    except Exception as e:
        print(f"Warning: intraday fetch failed for {ticker}: {e}")
        return {"hist": None, "prev_close": None}


def get_intraday_prices():
    """Fetch today's 1-minute prices and previous close for SPY and QQQ.

    Result: {ticker: {"hist": DataFrame|None with 'Close' column, "prev_close": float|None}}
    """
    with ThreadPoolExecutor(max_workers=len(INTRADAY_TICKERS)) as ex:
        return dict(zip(
            INTRADAY_TICKERS,
            ex.map(_fetch_intraday, INTRADAY_TICKERS)))


def load_and_compute(status_cb=None):
    if status_cb:
        status_cb("Loading holdings...")
    df = ubs_live_price_holdings()
    df2 = ubs_401k_holdings()
    df = pd.concat([df, df2], ignore_index=True)

    if status_cb:
        status_cb("Getting prices...")
    tickers = df['Ticker Alias'].tolist()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = dict(zip(tickers, executor.map(get_price_data, tickers)))
    df[['Last Price', 'Last Close', '% Move On Day']] = (
        df['Ticker Alias'].map(results).apply(pd.Series)
    )

    if status_cb:
        status_cb("Calculating PnL...")
    df['PnL'] = df['SOD VALUE'] * df['% Move On Day']

    return df.reset_index(drop=True)
