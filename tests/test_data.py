from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import data
from data import HighCache, _detect_split_ratio, validate_ticker


# ---------- _detect_split_ratio ----------

@pytest.mark.parametrize("price, close, expected", [
    (100.0, 100.0, 1),       # no split
    (16.67, 100.0, 6),       # 6:1 split (ratio = 0.167)
    (25.0, 100.0, 4),        # 4:1 split (ratio = 0.25)
    (50.0, 100.0, 1),        # ratio = 0.5 >= 0.35 threshold → not a split
    (35.0, 100.0, 1),        # at threshold (ratio = 0.35) → not a split
    (34.9, 100.0, 3),        # just below threshold → treated as 3:1 split
    (100.0, 95.0, 1),        # normal up day
    (95.0, 100.0, 1),        # normal down day
])
def test_detect_split_ratio(price, close, expected):
    assert _detect_split_ratio(price, close) == expected


# ---------- HighCache ----------

def test_high_cache_get_or_fetch_caches_per_day():
    cache = HighCache()
    fetcher = MagicMock(return_value={"6W": 100.0, "ATH": 200.0})
    today = pd.Timestamp("2026-01-15").date()

    cache.get_or_fetch("XLE", today, fetcher=fetcher)
    cache.get_or_fetch("XLE", today, fetcher=fetcher)  # second call same day
    assert fetcher.call_count == 1


def test_high_cache_refetches_next_day():
    cache = HighCache()
    fetcher = MagicMock(return_value={"6W": 100.0, "ATH": 200.0})
    day1 = pd.Timestamp("2026-01-15").date()
    day2 = pd.Timestamp("2026-01-16").date()

    cache.get_or_fetch("XLE", day1, fetcher=fetcher)
    cache.get_or_fetch("XLE", day2, fetcher=fetcher)
    assert fetcher.call_count == 2


def test_high_cache_bump_raises_high_on_overshoot():
    cache = HighCache()
    today = pd.Timestamp("2026-01-15").date()
    cache.get_or_fetch("XLE", today,
                      fetcher=lambda _t: {"6W": 100.0, "ATH": 200.0})
    cache.bump("XLE", 150.0)
    stored = cache.get_or_fetch("XLE", today, fetcher=MagicMock())
    assert stored["6W"] == 150.0
    assert stored["ATH"] == 200.0  # 150 < 200, unchanged


def test_high_cache_bump_handles_unknown_ticker():
    cache = HighCache()
    cache.bump("UNKNOWN", 999.0)  # should not raise


def test_high_cache_clear():
    cache = HighCache()
    today = pd.Timestamp("2026-01-15").date()
    cache.get_or_fetch("XLE", today,
                      fetcher=lambda _t: {"6W": 100.0, "ATH": 200.0})
    cache.clear()
    fetcher = MagicMock(return_value={"6W": 100.0, "ATH": 200.0})
    cache.get_or_fetch("XLE", today, fetcher=fetcher)
    assert fetcher.call_count == 1


# ---------- validate_ticker ----------

def test_validate_ticker_returns_true_for_positive_price():
    fast_info = MagicMock(last_price=180.5)
    with patch.object(data, "yf") as yf_mock:
        yf_mock.Ticker.return_value.fast_info = fast_info
        assert validate_ticker("AAPL") is True


def test_validate_ticker_returns_false_for_zero_price():
    fast_info = MagicMock(last_price=0.0)
    with patch.object(data, "yf") as yf_mock:
        yf_mock.Ticker.return_value.fast_info = fast_info
        assert validate_ticker("AAPL") is False


def test_validate_ticker_returns_false_on_exception():
    with patch.object(data, "yf") as yf_mock:
        yf_mock.Ticker.side_effect = KeyError("bogus")
        assert validate_ticker("NOTAREAL") is False


# ---------- _fetch_drawdown ----------

def test_fetch_drawdown_returns_negative_below_high():
    data._high_cache.clear()
    fast_info = MagicMock(last_price=90.0,
                          regular_market_previous_close=88.0)
    with patch.object(data, "yf") as yf_mock, \
         patch.object(data, "_fetch_highs",
                      return_value={"6W": 100.0, "ATH": 120.0}):
        yf_mock.Ticker.return_value.fast_info = fast_info
        dd = data._fetch_drawdown("XLE")
    assert dd["Today"] == pytest.approx((90 - 88) / 88)
    assert dd["6W"] == pytest.approx(-0.10)
    assert dd["ATH"] == pytest.approx(-0.25)


def test_fetch_drawdown_bumps_high_on_overshoot():
    data._high_cache.clear()
    fast_info = MagicMock(last_price=110.0,
                          regular_market_previous_close=108.0)
    with patch.object(data, "yf") as yf_mock, \
         patch.object(data, "_fetch_highs",
                      return_value={"6W": 100.0, "ATH": 120.0}):
        yf_mock.Ticker.return_value.fast_info = fast_info
        dd = data._fetch_drawdown("XLE")
    # last_price (110) exceeded 6W high (100) → bumped → drawdown = 0
    assert dd["Today"] == pytest.approx((110 - 108) / 108)
    assert dd["6W"] == 0.0
    assert dd["ATH"] == pytest.approx((110 - 120) / 120)


def test_fetch_drawdown_returns_none_on_exception():
    data._high_cache.clear()
    with patch.object(data, "yf") as yf_mock:
        yf_mock.Ticker.side_effect = KeyError("bogus")
        dd = data._fetch_drawdown("XLE")
    assert dd == {"Today": None, "6W": None, "ATH": None}
