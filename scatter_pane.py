import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from charts import draw_scatter


class ScatterPane:
    """SOD VALUE vs PnL (or Return) scatter, with hover tooltips."""

    def __init__(
        self,
        paned: ttk.PanedWindow,
        *,
        weight: int,
        hover_text: Callable[[pd.Series, float, float, bool, bool, pd.DataFrame], Optional[str]],
        tooltip,
    ):
        self._hover_text = hover_text
        self._tooltip = tooltip
        self._plot_df: pd.DataFrame | None = None
        self._scatter_df: pd.DataFrame | None = None
        self._log_x = False
        self._grouped = False
        self._return_mode = False

        frame = tk.Frame(paned, highlightbackground='black', highlightthickness=2)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        paned.add(frame, weight=weight)

        self._fig, self._ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
        self._fig.patch.set_facecolor('none')
        self._ax.set_xlabel("SOD VALUE ($)")
        self._ax.set_ylabel("PnL ($)")
        self._canvas = FigureCanvasTkAgg(self._fig, master=frame)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._fig.canvas.mpl_connect('motion_notify_event', self._on_hover)

    @property
    def scatter_df(self) -> pd.DataFrame | None:
        return self._scatter_df

    def redraw(self, plot_df: pd.DataFrame | None, *,
               log_x: bool, grouped: bool, return_mode: bool) -> None:
        self._plot_df = plot_df
        self._log_x = log_x
        self._grouped = grouped
        self._return_mode = return_mode
        if plot_df is None:
            return
        self._scatter_df = draw_scatter(
            self._ax, plot_df,
            log_x=log_x, grouped=grouped, return_mode=return_mode)
        self._canvas.draw()

    def toggle_log_x(self, enabled: bool) -> None:
        self._log_x = enabled
        if enabled:
            self._ax.set_xscale('log')
            self._ax.set_xlabel("SOD VALUE ($)  [log scale]")
        else:
            self._ax.set_xscale('linear')
            self._ax.set_xlabel("SOD VALUE ($)")
        self._canvas.draw()

    def _on_hover(self, event):
        if (event.inaxes != self._ax
                or not self._ax.collections
                or self._scatter_df is None
                or self._plot_df is None):
            self._tooltip.hide()
            return
        for coll in self._ax.collections:
            hit, ind = coll.contains(event)
            if hit:
                i = ind['ind'][0]
                x, y = coll.get_offsets()[i]
                row = self._scatter_df.iloc[i]
                text = self._hover_text(row, float(x), float(y),
                                        self._return_mode, self._grouped,
                                        self._plot_df)
                if text is not None:
                    self._tooltip.show(text, self._canvas.get_tk_widget(), event)
                    return
        self._tooltip.hide()
