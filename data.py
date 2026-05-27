import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

import pandas as pd
import yfinance as yf
from claudedev_shared import ubs_live_price_holdings, ubs_401k_holdings

from constants import Col

log = logging.getLogger(__name__)

SPLIT_THRESHOLD = 0.35  # if last/close ratio < this, assume a stock split

PriceTuple = tuple[float | None, float | None, float | None]
Drawdowns = dict[str, dict[str, float | None]]


def _detect_split_ratio(last_price: float, last_close: float) -> int:
    """If last_price/last_close suggests a split, return the integer ratio (e.g. 6).
    Returns 1 if no split detected."""
    ratio = last_price / last_close
    if ratio >= SPLIT_THRESHOLD:
        return 1
    inverse = round(1 / ratio)
    if inverse >= 2:
        return inverse
    return 1


_PRICE_FETCH_ERRORS = (AttributeError, KeyError, ValueError, OSError)


def get_price_data(ticker: str) -> PriceTuple:
    for attempt in range(2):
        try:
            data = yf.Ticker(ticker).fast_info
            last_price = data.last_price
            last_close = data.regular_market_previous_close
            split_ratio = _detect_split_ratio(last_price, last_close)
            if split_ratio > 1:
                last_close = last_close / split_ratio
                log.info("detected %d:1 split for %s, adjusted close to $%.2f",
                         split_ratio, ticker, last_close)
            pct_move = (last_price - last_close) / last_close
            return last_price, last_close, pct_move
        except _PRICE_FETCH_ERRORS as e:
            if attempt == 0:
                time.sleep(0.5)
            else:
                log.warning("failed to get price for %s: %s", ticker, e)
    return None, None, None


DEFAULT_TICKERS = ("SPY", "QQQ", "IWM", "EEM")


def _fetch_highs(ticker: str) -> dict[str, float | None]:
    t = yf.Ticker(ticker)
    six_weeks_ago = (pd.Timestamp.today() - pd.Timedelta(weeks=6)).strftime("%Y-%m-%d")
    hist_6w = t.history(start=six_weeks_ago, auto_adjust=False)
    hist_max = t.history(period="max", auto_adjust=False)
    return {
        "6W": float(hist_6w["High"].max()) if not hist_6w.empty else None,
        "ATH": float(hist_max["High"].max()) if not hist_max.empty else None,
    }


class HighCache:
    """Per-ticker cache of 6W/ATH highs.

    Highs refresh once per calendar day; `last_price` is fetched on every call
    so the drawdown stays current. If `last_price` exceeds the cached high
    intraday, `bump` updates the cache so we never report a positive drawdown.
    """

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get_or_fetch(self, ticker: str, today, fetcher=None) -> dict:
        # Default to module-level _fetch_highs, looked up dynamically so tests
        # can patch.object(data, "_fetch_highs", ...) and have it take effect.
        if fetcher is None:
            fetcher = _fetch_highs
        cached = self._store.get(ticker)
        if cached is None or cached["as_of"] != today:
            cached = {**fetcher(ticker), "as_of": today}
            self._store[ticker] = cached
        return cached

    def bump(self, ticker: str, last_price: float) -> None:
        cached = self._store.get(ticker)
        if cached is None:
            return
        for key in ("6W", "ATH"):
            if cached[key] is not None and last_price > cached[key]:
                cached[key] = last_price

    def clear(self) -> None:
        self._store.clear()


_high_cache = HighCache()


def _fetch_drawdown(ticker: str) -> dict[str, float | None]:
    try:
        fast_info = yf.Ticker(ticker).fast_info
        last_price = fast_info.last_price
        try:
            last_close = fast_info.regular_market_previous_close
            split_ratio = _detect_split_ratio(last_price, last_close)
            if split_ratio > 1:
                last_close = last_close / split_ratio
            today_pct = (last_price - last_close) / last_close
        except _PRICE_FETCH_ERRORS:
            today_pct = None
        today = pd.Timestamp.today().date()
        _high_cache.get_or_fetch(ticker, today)
        _high_cache.bump(ticker, last_price)
        cached = _high_cache.get_or_fetch(ticker, today)
        high_6w = cached["6W"]
        high_ath = cached["ATH"]
        return {
            "Today": today_pct,
            "6W": (last_price - high_6w) / high_6w if high_6w else None,
            "ATH": (last_price - high_ath) / high_ath if high_ath else None,
        }
    except _PRICE_FETCH_ERRORS as e:
        log.warning("drawdown fetch failed for %s: %s", ticker, e)
        return {"Today": None, "6W": None, "ATH": None}


def get_default_drawdowns() -> Drawdowns:
    """Return % drawdown of the default ticker set from 6-week and all-time highs.

    Result: {ticker: {"6W": decimal_or_None, "ATH": decimal_or_None}}
    """
    return get_drawdowns(DEFAULT_TICKERS)


def get_drawdowns(tickers: Iterable[str]) -> Drawdowns:
    """Generalized drawdown fetch for any ticker list."""
    tickers = tuple(tickers)
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=max(2, len(tickers))) as ex:
        return dict(zip(tickers, ex.map(_fetch_drawdown, tickers)))


def validate_ticker(ticker: str) -> bool:
    """Return True if `ticker` has a usable last_price on yfinance."""
    try:
        last = yf.Ticker(ticker).fast_info.last_price
        return last is not None and float(last) > 0
    except _PRICE_FETCH_ERRORS:
        return False


INTRADAY_TICKERS = ("SPY", "QQQ", "IWM")


def _fetch_intraday(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="1m", prepost=False)
        prev_close = None
        try:
            prev_close = float(t.fast_info.regular_market_previous_close)
        except _PRICE_FETCH_ERRORS:
            pass
        if hist is None or hist.empty:
            return {"hist": None, "prev_close": prev_close}
        return {"hist": hist[["Close"]], "prev_close": prev_close}
    except _PRICE_FETCH_ERRORS as e:
        log.warning("intraday fetch failed for %s: %s", ticker, e)
        return {"hist": None, "prev_close": None}


def get_intraday_prices() -> dict[str, dict]:
    """Fetch today's 1-minute prices and previous close for the intraday ticker set.

    Result: {ticker: {"hist": DataFrame|None with 'Close' column, "prev_close": float|None}}
    """
    with ThreadPoolExecutor(max_workers=len(INTRADAY_TICKERS)) as ex:
        return dict(zip(
            INTRADAY_TICKERS,
            ex.map(_fetch_intraday, INTRADAY_TICKERS)))


def load_and_compute(status_cb: Callable[[str], None] | None = None) -> pd.DataFrame:
    if status_cb:
        status_cb("Loading holdings...")
    df = ubs_live_price_holdings()
    df2 = ubs_401k_holdings()
    df = pd.concat([df, df2], ignore_index=True)

    if status_cb:
        status_cb("Getting prices...")
    tickers = df[Col.TICKER].tolist()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = dict(zip(tickers, executor.map(get_price_data, tickers)))
    df[[Col.LAST_PRICE, Col.LAST_CLOSE, Col.PCT_MOVE]] = (
        df[Col.TICKER].map(results).apply(pd.Series)
    )

    if status_cb:
        status_cb("Calculating PnL...")
    df[Col.PNL] = df[Col.SOD_VALUE] * df[Col.PCT_MOVE]

    return df.reset_index(drop=True)
