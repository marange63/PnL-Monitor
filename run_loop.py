import threading
import traceback
from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd
import tkinter as tk

from data import (
    load_and_compute, get_default_drawdowns, get_drawdowns, get_intraday_prices,
)


@dataclass
class RunResult:
    plot_df: pd.DataFrame
    etf_dd: dict
    custom_dd: dict
    intraday: dict


class RunLoop:
    """Runs the data-fetch worker on demand or on an interval timer.

    The caller supplies:
      - `custom_tickers_provider()`         → current list of custom tickers
      - `on_result(RunResult)`              → called on the main thread when data is ready
      - `on_status(str)`                    → main-thread status updates
      - `on_busy(bool)`                     → toggled before/after each run
      - `on_auto_label(str)`                → updates the Auto Update button label
    """

    def __init__(
        self,
        root: tk.Tk,
        *,
        interval_ms: int,
        countdown_secs: int,
        custom_tickers_provider: Callable[[], list[str]],
        on_result: Callable[[RunResult], None],
        on_status: Callable[[str], None],
        on_busy: Callable[[bool], None],
        on_auto_label: Callable[[str], None],
    ):
        self._root = root
        self._interval_ms = interval_ms
        self._countdown_secs = countdown_secs
        self._custom_tickers = custom_tickers_provider
        self._on_result = on_result
        self._on_status = on_status
        self._on_busy = on_busy
        self._on_auto_label = on_auto_label

        self.auto_running = False
        self._auto_after_id: Optional[str] = None
        self._countdown_id: Optional[str] = None

    # -- public API ----------------------------------------------------------

    def run_once(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def toggle_auto(self) -> None:
        if not self.auto_running:
            self.auto_running = True
            self._start_auto_run()
        else:
            self.auto_running = False
            self._on_auto_label("Auto Update")
            if self._auto_after_id:
                self._root.after_cancel(self._auto_after_id)
                self._auto_after_id = None
            if self._countdown_id:
                self._root.after_cancel(self._countdown_id)
                self._countdown_id = None

    # -- internals -----------------------------------------------------------

    def _start_auto_run(self) -> None:
        if self.auto_running:
            threading.Thread(target=self._auto_worker, daemon=True).start()

    def _auto_worker(self) -> None:
        self._root.after(0, lambda: self._on_auto_label("Stop"))
        self._worker()
        if self.auto_running:
            self._auto_after_id = self._root.after(
                self._interval_ms, self._start_auto_run)
            self._root.after(0, lambda: self._start_countdown(self._countdown_secs))

    def _start_countdown(self, secs_left: int) -> None:
        if not self.auto_running:
            return
        self._on_auto_label(f"Stop ({secs_left}s)")
        if secs_left > 0:
            self._countdown_id = self._root.after(
                1000, lambda: self._start_countdown(secs_left - 1))

    def _worker(self) -> None:
        self._root.after(0, lambda: self._on_busy(True))
        try:
            df = load_and_compute(
                status_cb=lambda msg: self._root.after(
                    0, lambda m=msg: self._on_status(m)))

            self._root.after(0, lambda: self._on_status("Fetching highs..."))
            etf_dd = get_default_drawdowns()
            custom_dd = get_drawdowns(self._custom_tickers())

            self._root.after(0, lambda: self._on_status("Fetching intraday prices..."))
            intraday = get_intraday_prices()

            result = RunResult(plot_df=df, etf_dd=etf_dd,
                               custom_dd=custom_dd, intraday=intraday)
            self._root.after(0, lambda: self._on_result(result))
        except Exception as e:
            traceback.print_exc()
            self._root.after(0, lambda: self._on_status(f"Error: {e}"))
        finally:
            self._root.after(0, lambda: self._on_busy(False))
