from tkinter import ttk
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection

from constants import PNL_POS_COLOR, PNL_NEG_COLOR


class IntradayChartGrid(ttk.LabelFrame):
    """Row of small % return vs prev-close charts, one per ticker."""

    def __init__(self, parent, tickers: tuple[str, ...], tz: ZoneInfo):
        super().__init__(parent, text="Intraday", padding=(8, 6))
        self._tz = tz
        self._figs = {}
        self._axes = {}
        self._canvases = {}
        for col, tkr in enumerate(tickers):
            fig, ax = plt.subplots(figsize=(2.4, 1.4), constrained_layout=True)
            fig.patch.set_facecolor('none')
            ax.set_title(tkr, fontsize=9)
            ax.tick_params(axis='both', labelsize=7)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            canvas = FigureCanvasTkAgg(fig, master=self)
            canvas.get_tk_widget().grid(row=0, column=col, padx=4, pady=2)
            self._figs[tkr] = fig
            self._axes[tkr] = ax
            self._canvases[tkr] = canvas

    def update(self, intraday_data: dict) -> None:
        # Pass 1: compute % return series per ticker and find a shared y-range
        series = {}
        y_min, y_max = 0.0, 0.0
        for tkr in self._axes:
            entry = intraday_data.get(tkr) or {}
            hist = entry.get("hist")
            prev_close = entry.get("prev_close")
            if hist is None or hist.empty:
                series[tkr] = None
                continue
            ref = prev_close if prev_close else float(hist["Close"].iloc[0])
            pct = (hist["Close"] - ref) / ref * 100.0
            series[tkr] = (hist.index, pct)
            y_min = min(y_min, float(pct.min()))
            y_max = max(y_max, float(pct.max()))

        margin = max(0.05, (y_max - y_min) * 0.1)
        y_min -= margin
        y_max += margin

        # Pass 2: draw each chart with the shared y-range
        for tkr, ax in self._axes.items():
            ax.clear()
            ax.tick_params(axis='both', labelsize=7)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            data = series[tkr]
            if data is None:
                ax.set_title(f"{tkr}  —", fontsize=9, color="gray")
                self._canvases[tkr].draw()
                continue
            idx, pct = data
            last_pct = float(pct.iloc[-1])
            title_color = PNL_POS_COLOR if last_pct >= 0 else PNL_NEG_COLOR

            x = mdates.date2num(idx.to_pydatetime())
            y = pct.to_numpy()
            points = np.array([x, y]).T.reshape(-1, 1, 2)
            segments = np.concatenate([points[:-1], points[1:]], axis=1)
            seg_mid = (y[:-1] + y[1:]) / 2.0
            seg_colors = np.where(seg_mid >= 0, PNL_POS_COLOR, PNL_NEG_COLOR)
            ax.add_collection(LineCollection(segments, colors=seg_colors,
                                             linewidth=1.2))

            ax.axhline(0, color="gray", linestyle=":", linewidth=0.7)
            ax.set_xlim(x[0], x[-1])
            ax.set_ylim(y_min, y_max)
            ax.set_title(f"{tkr}  {last_pct:+.2f}%", fontsize=9, color=title_color)
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=self._tz))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H', tz=self._tz))
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _pos: f"{v:+.1f}%"))
            self._canvases[tkr].draw()
