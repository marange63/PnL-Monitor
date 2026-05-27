import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from charts import draw_bar
from constants import (
    BAR_ROW_HEIGHT_INCHES, BAR_MIN_HEIGHT_INCHES, BAR_RESIZE_DEBOUNCE_MS,
)


class ScrollableBarChart:
    """A scrollable horizontal bar chart pane.

    Caller provides a `build_df(plot_df, **opts)` callable that returns a
    DataFrame with at least 'Label' and 'Value' columns. `hover_text(row, plot_df)`
    returns the tooltip text for a hovered bar (or None to hide).

    The pane registers itself into the supplied PanedWindow with the given weight.
    """

    def __init__(
        self,
        paned: ttk.PanedWindow,
        root: tk.Tk,
        *,
        weight: int,
        build_df: Callable[..., pd.DataFrame],
        hover_text: Callable[[pd.Series, pd.DataFrame], Optional[str]],
        tooltip,
        figsize: tuple[float, float] = (4.0, 6.0),
    ):
        self._root = root
        self._build_df = build_df
        self._hover_text = hover_text
        self._tooltip = tooltip
        self._plot_df: pd.DataFrame | None = None
        self._current_df: pd.DataFrame | None = None
        self._resize_after_id: Optional[str] = None

        outer = tk.Frame(paned, highlightbackground='black', highlightthickness=2)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        paned.add(outer, weight=weight)

        self._scroll_canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical",
                                  command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self._fig, self._ax = plt.subplots(figsize=figsize, constrained_layout=True)
        self._fig.patch.set_facecolor('none')
        self._ax.set_xlabel("PnL ($)")

        self._canvas = FigureCanvasTkAgg(self._fig, master=self._scroll_canvas)
        self._canvas_widget = self._canvas.get_tk_widget()
        self._window_id = self._scroll_canvas.create_window(
            0, 0, anchor="nw", window=self._canvas_widget)

        self._scroll_canvas.bind("<Configure>", self._on_area_resize)
        self._scroll_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas_widget.bind("<MouseWheel>", self._on_mousewheel)
        self._fig.canvas.mpl_connect('motion_notify_event', self._on_hover)

    # -- public API ----------------------------------------------------------

    @property
    def current_df(self) -> pd.DataFrame | None:
        return self._current_df

    def redraw(self, plot_df: pd.DataFrame | None, **build_opts) -> None:
        self._plot_df = plot_df
        if plot_df is None:
            return
        df = self._build_df(plot_df, **build_opts)
        draw_bar(self._ax, df, return_mode=build_opts.get('return_mode', False))
        self._current_df = df

        n = len(df)
        w_px = max(self._canvas_widget.winfo_width(), 100)
        h_px = int(max(BAR_MIN_HEIGHT_INCHES, n * BAR_ROW_HEIGHT_INCHES)
                   * self._ax.figure.dpi)
        self._canvas_widget.config(width=w_px, height=h_px)
        self._scroll_canvas.itemconfigure(self._window_id, width=w_px)
        self._scroll_canvas.configure(scrollregion=(0, 0, w_px, h_px))
        self._canvas.draw()

    # -- event handlers ------------------------------------------------------

    def _on_area_resize(self, event):
        w = event.width
        if self._resize_after_id:
            self._root.after_cancel(self._resize_after_id)
        self._resize_after_id = self._root.after(
            BAR_RESIZE_DEBOUNCE_MS, lambda: self._do_resize(w))

    def _do_resize(self, w: int):
        if w < 10:
            return
        h_px = int(self._fig.get_figheight() * self._fig.dpi)
        self._canvas_widget.config(width=w, height=h_px)
        self._scroll_canvas.itemconfigure(self._window_id, width=w)
        self._scroll_canvas.configure(scrollregion=(0, 0, w, h_px))

    def _on_mousewheel(self, event):
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_hover(self, event):
        if (event.inaxes != self._ax
                or self._current_df is None
                or event.ydata is None
                or self._plot_df is None):
            self._tooltip.hide()
            return
        i = round(event.ydata)
        n = len(self._current_df)
        if 0 <= i < n and abs(event.ydata - i) <= 0.4:
            row = self._current_df.iloc[i]
            text = self._hover_text(row, self._plot_df)
            if text is not None:
                self._tooltip.show(text, self._canvas_widget, event)
                return
        self._tooltip.hide()
