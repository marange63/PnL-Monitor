import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from charts import draw_treemap

TREEMAP_RESIZE_DEBOUNCE_MS = 150


class TreemapPane:
    """Treemap of positions, sized by |PnL|, colored by sign of % move."""

    def __init__(
        self,
        paned: ttk.PanedWindow,
        root: tk.Tk,
        *,
        weight: int,
        hover_text: Callable[[pd.Series, dict], Optional[str]],
        tooltip,
    ):
        self._root = root
        self._hover_text = hover_text
        self._tooltip = tooltip
        self._plot_df: pd.DataFrame | None = None
        self._rects: list = []
        self._df: pd.DataFrame | None = None
        self._grouped = False
        self._resize_after_id: str | None = None

        frame = tk.Frame(paned)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        paned.add(frame, weight=weight)

        self._fig, self._ax = plt.subplots(figsize=(5, 4), constrained_layout=True)
        self._fig.patch.set_facecolor('none')
        self._ax.set_axis_off()

        self._canvas = FigureCanvasTkAgg(self._fig, master=frame)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._fig.canvas.mpl_connect('motion_notify_event', self._on_hover)
        frame.bind("<Configure>", self._on_frame_resize)

    def redraw(self, plot_df: pd.DataFrame | None, *, grouped: bool) -> None:
        self._plot_df = plot_df
        self._grouped = grouped
        if plot_df is None:
            return
        self._rects, self._df = draw_treemap(self._ax, plot_df, grouped=grouped)
        self._canvas.draw()

    def _on_frame_resize(self, _event):
        if self._resize_after_id:
            self._root.after_cancel(self._resize_after_id)
        self._resize_after_id = self._root.after(
            TREEMAP_RESIZE_DEBOUNCE_MS, self._redraw_current)

    def _redraw_current(self):
        self.redraw(self._plot_df, grouped=self._grouped)

    def _on_hover(self, event):
        if (event.inaxes != self._ax
                or not self._rects
                or event.xdata is None
                or self._df is None):
            self._tooltip.hide()
            return
        for i, rect in enumerate(self._rects):
            if (rect['x'] <= event.xdata <= rect['x'] + rect['dx'] and
                    rect['y'] <= event.ydata <= rect['y'] + rect['dy']):
                row = self._df.iloc[i]
                text = self._hover_text(row, rect)
                if text is not None:
                    self._tooltip.show(text, self._canvas.get_tk_widget(), event)
                    return
        self._tooltip.hide()
