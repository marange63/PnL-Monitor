from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

import notify_pnl


def test_load_with_retry_recovers_after_rate_limit():
    df = pd.DataFrame()
    load = MagicMock(side_effect=[YFRateLimitError(), YFRateLimitError(), df])
    with patch.object(notify_pnl, "load_and_compute", load), \
         patch.object(notify_pnl._time, "sleep") as sleep:
        assert notify_pnl.load_with_retry() is df
    assert [c.args[0] for c in sleep.call_args_list] == [30, 60]


def test_load_with_retry_gives_up_after_backoff_exhausted():
    load = MagicMock(side_effect=YFRateLimitError())
    with patch.object(notify_pnl, "load_and_compute", load), \
         patch.object(notify_pnl._time, "sleep"):
        with pytest.raises(YFRateLimitError):
            notify_pnl.load_with_retry()
    assert load.call_count == len(notify_pnl.RATE_LIMIT_BACKOFF_SECS) + 1


def test_load_with_retry_does_not_retry_other_errors():
    load = MagicMock(side_effect=ValueError("bad csv"))
    with patch.object(notify_pnl, "load_and_compute", load), \
         patch.object(notify_pnl._time, "sleep") as sleep:
        with pytest.raises(ValueError):
            notify_pnl.load_with_retry()
    assert load.call_count == 1
    sleep.assert_not_called()
