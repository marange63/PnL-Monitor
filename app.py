import datetime
import json
import os
import threading
import traceback
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

ET_TZ = ZoneInfo("America/New_York")

import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import font as tkfont, filedialog, ttk
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection

from constants import (
    AUTO_UPDATE_INTERVAL_MS, AUTO_UPDATE_COUNTDOWN_SECS,
    BAR_ROW_HEIGHT_INCHES, BAR_MIN_HEIGHT_INCHES, BAR_RESIZE_DEBOUNCE_MS,
    PNL_POS_COLOR, PNL_NEG_COLOR,
)
from data import (
    load_and_compute, get_etf_drawdowns, ETF_DRAWDOWN_TICKERS,
    get_intraday_prices, INTRADAY_TICKERS,
    get_drawdowns, validate_ticker,
)
from charts import draw_scatter, build_bar_df, draw_bar, build_tag_bar_df, draw_treemap

MAX_CUSTOM_TICKERS = 4
CUSTOM_TICKERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "custom_tickers.json")


def _load_custom_tickers():
    try:
        with open(CUSTOM_TICKERS_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [str(t).upper() for t in data][:MAX_CUSTOM_TICKERS]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_custom_tickers(tickers):
    with open(CUSTOM_TICKERS_FILE, "w") as f:
        json.dump(list(tickers), f)


@dataclass
class AppState:
    plot_df: Optional[pd.DataFrame] = None      # full per-position DataFrame
    scatter_df: Optional[pd.DataFrame] = None   # what's currently plotted (may be grouped)
    current_bar_df: Optional[pd.DataFrame] = None
    current_tag_bar_df: Optional[pd.DataFrame] = None
    treemap_rects: Optional[list] = None
    treemap_df: Optional[pd.DataFrame] = None
    auto_running: bool = False
    auto_after_id: Optional[str] = None
    countdown_id: Optional[str] = None
    bar_resize_id: Optional[str] = None
    tag_bar_resize_id: Optional[str] = None
    treemap_resize_id: Optional[str] = None


class PnLApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state = AppState()

        root.title("PnL Monitor")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        self._label_font = tkfont.Font(family="Segoe UI", size=11)
        self._value_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        self.paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self._build_controls()
        self._build_treemap()
        self._build_scatter()
        self._build_bar()
        self._build_tag_bar()
        self._build_tooltip()

    # ------------------------------------------------------------------ build

    def _action_btn(self, parent, text, command, width=12):
        return tk.Button(
            parent, text=text, width=width, command=command,
            font=self._label_font,
            bg='#2d5a9e', fg='white',
            activebackground='#3a6fbf', activeforeground='white',
            disabledforeground='#8899bb',
            relief='raised', bd=3, padx=8, cursor='hand2',
        )

    def _build_controls(self):
        pad = {"padx": 16, "pady": 8}
        ctrl = ttk.Frame(self.root)
        ctrl.grid(row=0, column=0, sticky="ew")
        ctrl.columnconfigure(0, weight=0)
        ctrl.columnconfigure(1, weight=0)
        ctrl.columnconfigure(2, weight=1)

        self._build_etf_table(ctrl)
        self._build_custom_table(ctrl)
        self._build_intraday_charts(ctrl)

        btn_frame = ttk.Frame(ctrl)
        btn_frame.grid(row=0, column=2, **pad)

        self.run_btn = self._action_btn(
            btn_frame, "Run", width=10,
            command=lambda: threading.Thread(
                target=self._run_worker, daemon=True).start())
        self.run_btn.grid(row=0, column=0, padx=(0, 8))

        self.auto_btn = self._action_btn(
            btn_frame, "Auto Update", width=13,
            command=self.toggle_auto)
        self.auto_btn.grid(row=0, column=1, padx=(8, 16))

        ttk.Separator(btn_frame, orient=tk.VERTICAL).grid(
            row=0, column=2, sticky="ns", padx=(0, 8))

        self.log_x_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            btn_frame, text="Log X axis",
            variable=self.log_x_var, command=self._toggle_log_x
        ).grid(row=0, column=3, padx=(0, 8))

        self.group_scatter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            btn_frame, text="Group Tickers",
            variable=self.group_scatter_var, command=self._toggle_group
        ).grid(row=0, column=4, padx=(0, 8))

        self.return_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            btn_frame, text="Return %",
            variable=self.return_mode_var, command=self._redraw_all
        ).grid(row=0, column=5, padx=(0, 8))

        self.sort_by_name = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            btn_frame, text="Sort A–Z",
            variable=self.sort_by_name, command=self._redraw_bars
        ).grid(row=0, column=6)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).grid(
            row=0, column=7, sticky="ns", padx=(8, 0))

        self._action_btn(
            btn_frame, "Export CSV", width=12,
            command=self._export_scatter_csv
        ).grid(row=0, column=8, padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(ctrl, textvariable=self.status_var,
                  foreground="gray").grid(
            row=1, column=2, **pad)

        self.result_vars = {
            "UBS": tk.StringVar(value="—"),
            "401K": tk.StringVar(value="—"),
            "Total": tk.StringVar(value="—"),
        }

        fields = ttk.LabelFrame(ctrl, text="", padding=(12, 6))
        fields.grid(row=2, column=2, pady=(0, 12))

        self.pnl_labels = {}
        for col, (label_text, key) in enumerate(
                [("UBS PnL", "UBS"), ("401K PnL", "401K"), ("Total PnL", "Total")]):
            ttk.Label(fields, text=label_text,
                      font=self._label_font, anchor="center").grid(
                row=0, column=col, padx=24, pady=(4, 2))
            lbl = ttk.Label(fields, textvariable=self.result_vars[key],
                            font=self._value_font, width=12, anchor="center")
            lbl.grid(row=1, column=col, padx=24, pady=(0, 4))
            self.pnl_labels[key] = lbl

    def _build_etf_table(self, parent):
        self.etf_frame = ttk.LabelFrame(parent, text="ETF % from Highs", padding=(8, 6))
        self.etf_frame.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(8, 16), pady=8)

        ttk.Label(self.etf_frame, text="ETF", font=self._label_font,
                  anchor="center").grid(row=0, column=0, padx=8, pady=2)
        ttk.Label(self.etf_frame, text="6W High", font=self._label_font,
                  anchor="center").grid(row=0, column=1, padx=8, pady=2)
        ttk.Label(self.etf_frame, text="All-Time High", font=self._label_font,
                  anchor="center").grid(row=0, column=2, padx=8, pady=2)

        self.etf_vars = {}
        self.etf_labels = {}
        for i, tkr in enumerate(ETF_DRAWDOWN_TICKERS, start=1):
            ttk.Label(self.etf_frame, text=tkr, font=self._label_font,
                      anchor="center").grid(row=i, column=0, padx=8, pady=2)
            for col, key in enumerate(("6W", "ATH"), start=1):
                v = tk.StringVar(value="—")
                lbl = ttk.Label(self.etf_frame, textvariable=v, font=self._label_font,
                                anchor="e", width=8)
                lbl.grid(row=i, column=col, padx=8, pady=2)
                self.etf_vars[(tkr, key)] = v
                self.etf_labels[(tkr, key)] = lbl

    def _build_custom_table(self, parent):
        self.custom_tickers = _load_custom_tickers()
        self.custom_vars = {}
        self.custom_labels = {}
        self.custom_entry_var = tk.StringVar()

        self.custom_frame = ttk.LabelFrame(
            parent, text="Custom % from Highs", padding=(8, 6))
        self.custom_frame.grid(
            row=0, column=1, rowspan=3, sticky="nw", padx=(0, 16), pady=8)

        self._render_custom_table()

    def _render_custom_table(self):
        for w in self.custom_frame.winfo_children():
            w.destroy()
        self.custom_vars = {}
        self.custom_labels = {}

        ttk.Label(self.custom_frame, text="Ticker", font=self._label_font,
                  anchor="center").grid(row=0, column=0, padx=8, pady=2)
        ttk.Label(self.custom_frame, text="6W High", font=self._label_font,
                  anchor="center").grid(row=0, column=1, padx=8, pady=2)
        ttk.Label(self.custom_frame, text="All-Time High", font=self._label_font,
                  anchor="center").grid(row=0, column=2, padx=8, pady=2)

        for i, tkr in enumerate(self.custom_tickers, start=1):
            ttk.Label(self.custom_frame, text=tkr, font=self._label_font,
                      anchor="center").grid(row=i, column=0, padx=8, pady=2)
            for col, key in enumerate(("6W", "ATH"), start=1):
                v = tk.StringVar(value="—")
                lbl = ttk.Label(self.custom_frame, textvariable=v,
                                font=self._label_font, anchor="e", width=8)
                lbl.grid(row=i, column=col, padx=8, pady=2)
                self.custom_vars[(tkr, key)] = v
                self.custom_labels[(tkr, key)] = lbl
            del_lbl = ttk.Label(
                self.custom_frame, text="×", font=self._label_font,
                foreground="#b22222", cursor='hand2', anchor='center', width=2,
            )
            del_lbl.grid(row=i, column=3, padx=(2, 4), pady=2)
            del_lbl.bind("<Button-1>",
                         lambda _e, t=tkr: self._remove_custom_ticker(t))

        last_row = len(self.custom_tickers)

        # Add row appears only when there's room for another ticker
        if len(self.custom_tickers) < MAX_CUSTOM_TICKERS:
            add_row = last_row + 1
            self.custom_entry_var.set("")
            entry = ttk.Entry(self.custom_frame, textvariable=self.custom_entry_var,
                              width=8, font=self._label_font)
            entry.grid(row=add_row, column=0, padx=8, pady=2, sticky="ew")
            entry.bind("<Return>", lambda _e: self._add_custom_ticker())
            tk.Button(
                self.custom_frame, text="Add", width=5,
                command=self._add_custom_ticker,
                font=self._label_font,
                bg='#2d5a9e', fg='white',
                activebackground='#3a6fbf', activeforeground='white',
                relief='raised', bd=2, cursor='hand2',
            ).grid(row=add_row, column=1, columnspan=3,
                   padx=4, pady=2, sticky="w")
            last_row = add_row

        # Pad with empty rows so the pane height matches the ETF pane
        # (header + MAX_CUSTOM_TICKERS rows)
        for filler_row in range(last_row + 1, MAX_CUSTOM_TICKERS + 1):
            ttk.Label(self.custom_frame, text=" ", font=self._label_font,
                      anchor="center").grid(row=filler_row, column=0,
                                            padx=8, pady=2)

        # The Add row's Entry is taller than a Label, so the natural height
        # exceeds the ETF pane. Pin the frame to the ETF pane's height.
        self.root.after_idle(self._sync_custom_pane_height)

    def _sync_custom_pane_height(self):
        self.custom_frame.grid_propagate(True)
        self.custom_frame.update_idletasks()
        self.etf_frame.update_idletasks()
        natural_w = self.custom_frame.winfo_reqwidth()
        target_h = self.etf_frame.winfo_reqheight()
        self.custom_frame.config(width=natural_w, height=target_h)
        self.custom_frame.grid_propagate(False)

    def _add_custom_ticker(self):
        tkr = self.custom_entry_var.get().strip().upper()
        if not tkr:
            return
        if tkr in self.custom_tickers:
            self.status_var.set(f"{tkr} already in custom list")
            return
        if len(self.custom_tickers) >= MAX_CUSTOM_TICKERS:
            return
        self.status_var.set(f"Validating {tkr}...")
        threading.Thread(
            target=self._add_custom_ticker_worker, args=(tkr,), daemon=True
        ).start()

    def _add_custom_ticker_worker(self, tkr):
        valid = validate_ticker(tkr)

        def _finish():
            if not valid:
                self.status_var.set(f"Invalid ticker: {tkr}")
                return
            if tkr in self.custom_tickers:
                return
            if len(self.custom_tickers) >= MAX_CUSTOM_TICKERS:
                return
            self.custom_tickers.append(tkr)
            _save_custom_tickers(self.custom_tickers)
            self._render_custom_table()
            self.status_var.set(f"Added {tkr}")
            threading.Thread(
                target=self._refresh_custom_drawdowns, daemon=True
            ).start()

        self.root.after(0, _finish)

    def _remove_custom_ticker(self, tkr):
        if tkr in self.custom_tickers:
            self.custom_tickers.remove(tkr)
            _save_custom_tickers(self.custom_tickers)
            self._render_custom_table()

    def _refresh_custom_drawdowns(self):
        tickers = list(self.custom_tickers)
        if not tickers:
            return
        dd = get_drawdowns(tickers)
        self.root.after(0, lambda: self._update_custom_table(dd))

    def _update_custom_table(self, dd):
        for tkr, vals in dd.items():
            for key in ("6W", "ATH"):
                v = self.custom_vars.get((tkr, key))
                lbl = self.custom_labels.get((tkr, key))
                if v is None or lbl is None:
                    continue
                val = vals.get(key)
                if val is None:
                    v.set("—")
                    lbl.config(foreground="gray")
                else:
                    v.set(f"{val * 100:+.2f}%")
                    lbl.config(foreground=PNL_NEG_COLOR if val < 0 else PNL_POS_COLOR)

    def _build_intraday_charts(self, parent):
        frame = ttk.LabelFrame(parent, text="Intraday", padding=(8, 6))
        frame.grid(row=0, column=3, rowspan=3, sticky="ne", padx=(8, 8), pady=8)

        self.intraday_figs = {}
        self.intraday_axes = {}
        self.intraday_canvases = {}
        for col, tkr in enumerate(INTRADAY_TICKERS):
            fig, ax = plt.subplots(figsize=(2.4, 1.4), constrained_layout=True)
            fig.patch.set_facecolor('none')
            ax.set_title(tkr, fontsize=9)
            ax.tick_params(axis='both', labelsize=7)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            canvas = FigureCanvasTkAgg(fig, master=frame)
            canvas.get_tk_widget().grid(row=0, column=col, padx=4, pady=2)
            self.intraday_figs[tkr] = fig
            self.intraday_axes[tkr] = ax
            self.intraday_canvases[tkr] = canvas

    def _update_intraday_charts(self, intraday_data):
        # Pass 1: compute % return series per ticker and find a shared y-range
        series = {}
        y_min, y_max = 0.0, 0.0
        for tkr in self.intraday_axes:
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
        for tkr, ax in self.intraday_axes.items():
            ax.clear()
            ax.tick_params(axis='both', labelsize=7)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            data = series[tkr]
            if data is None:
                ax.set_title(f"{tkr}  —", fontsize=9, color="gray")
                self.intraday_canvases[tkr].draw()
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
            ax.add_collection(LineCollection(segments, colors=seg_colors, linewidth=1.2))

            ax.axhline(0, color="gray", linestyle=":", linewidth=0.7)
            ax.set_xlim(x[0], x[-1])
            ax.set_ylim(y_min, y_max)
            ax.set_title(f"{tkr}  {last_pct:+.2f}%", fontsize=9, color=title_color)
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=ET_TZ))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H', tz=ET_TZ))
            ax.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _pos: f"{v:+.1f}%"))
            self.intraday_canvases[tkr].draw()

    def _update_etf_table(self, etf_dd):
        for tkr, dd in etf_dd.items():
            for key in ("6W", "ATH"):
                val = dd.get(key)
                var = self.etf_vars[(tkr, key)]
                lbl = self.etf_labels[(tkr, key)]
                if val is None:
                    var.set("—")
                    lbl.config(foreground="gray")
                else:
                    var.set(f"{val * 100:+.2f}%")
                    lbl.config(foreground=PNL_NEG_COLOR if val < 0 else PNL_POS_COLOR)

    def _build_scatter(self):
        scatter_frame = tk.Frame(self.paned,
                                  highlightbackground='black', highlightthickness=2)
        scatter_frame.rowconfigure(0, weight=1)
        scatter_frame.columnconfigure(0, weight=1)
        self.paned.add(scatter_frame, weight=9)

        self.fig, self.ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
        self.fig.patch.set_facecolor('none')
        self.ax.set_xlabel("SOD VALUE ($)")
        self.ax.set_ylabel("PnL ($)")
        self.canvas = FigureCanvasTkAgg(self.fig, master=scatter_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_hover)

    def _build_bar(self):
        bar_outer = tk.Frame(self.paned,
                             highlightbackground='black', highlightthickness=2)
        bar_outer.rowconfigure(0, weight=1)
        bar_outer.columnconfigure(0, weight=1)
        self.paned.add(bar_outer, weight=6)

        self.bar_scroll_canvas = tk.Canvas(bar_outer, highlightthickness=0)
        bar_scrollbar = ttk.Scrollbar(
            bar_outer, orient="vertical", command=self.bar_scroll_canvas.yview)
        self.bar_scroll_canvas.configure(yscrollcommand=bar_scrollbar.set)
        bar_scrollbar.grid(row=0, column=1, sticky="ns")
        self.bar_scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self.bar_fig, self.ax_bar = plt.subplots(figsize=(4, 6), constrained_layout=True)
        self.bar_fig.patch.set_facecolor('none')
        self.ax_bar.set_xlabel("PnL ($)")

        self.bar_canvas = FigureCanvasTkAgg(self.bar_fig, master=self.bar_scroll_canvas)
        self.bar_canvas_widget = self.bar_canvas.get_tk_widget()
        self.bar_window_id = self.bar_scroll_canvas.create_window(
            0, 0, anchor="nw", window=self.bar_canvas_widget)

        self.bar_scroll_canvas.bind("<Configure>", self._on_bar_area_resize)
        self.bar_scroll_canvas.bind("<MouseWheel>", self._on_bar_mousewheel)
        self.bar_canvas_widget.bind("<MouseWheel>", self._on_bar_mousewheel)
        self.bar_fig.canvas.mpl_connect('motion_notify_event', self._on_bar_hover)

    def _build_tag_bar(self):
        tag_outer = tk.Frame(self.paned,
                             highlightbackground='black', highlightthickness=2)
        tag_outer.rowconfigure(0, weight=1)
        tag_outer.columnconfigure(0, weight=1)
        self.paned.add(tag_outer, weight=7)

        self.tag_scroll_canvas = tk.Canvas(tag_outer, highlightthickness=0)
        tag_scrollbar = ttk.Scrollbar(
            tag_outer, orient="vertical", command=self.tag_scroll_canvas.yview)
        self.tag_scroll_canvas.configure(yscrollcommand=tag_scrollbar.set)
        tag_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tag_scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self.tag_fig, self.ax_tag_bar = plt.subplots(figsize=(4, 6), constrained_layout=True)
        self.tag_fig.patch.set_facecolor('none')
        self.ax_tag_bar.set_xlabel("PnL ($)")

        self.tag_canvas = FigureCanvasTkAgg(self.tag_fig, master=self.tag_scroll_canvas)
        self.tag_canvas_widget = self.tag_canvas.get_tk_widget()
        self.tag_window_id = self.tag_scroll_canvas.create_window(
            0, 0, anchor="nw", window=self.tag_canvas_widget)

        self.tag_scroll_canvas.bind("<Configure>", self._on_tag_area_resize)
        self.tag_scroll_canvas.bind("<MouseWheel>", self._on_tag_mousewheel)
        self.tag_canvas_widget.bind("<MouseWheel>", self._on_tag_mousewheel)
        self.tag_fig.canvas.mpl_connect('motion_notify_event', self._on_tag_bar_hover)

    def _build_treemap(self):
        treemap_frame = tk.Frame(self.paned)
        treemap_frame.rowconfigure(0, weight=1)
        treemap_frame.columnconfigure(0, weight=1)
        self.paned.add(treemap_frame, weight=7)

        self.treemap_fig, self.ax_treemap = plt.subplots(
            figsize=(5, 4), constrained_layout=True)
        self.treemap_fig.patch.set_facecolor('none')
        self.ax_treemap.set_axis_off()

        self.treemap_canvas = FigureCanvasTkAgg(self.treemap_fig, master=treemap_frame)
        self.treemap_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.treemap_fig.canvas.mpl_connect('motion_notify_event', self._on_treemap_hover)
        treemap_frame.bind("<Configure>", self._on_treemap_resize)

    def _build_tooltip(self):
        self.tip_win = tk.Toplevel(self.root)
        self.tip_win.wm_overrideredirect(True)
        self.tip_win.withdraw()
        self.tip_label = tk.Label(
            self.tip_win, font=self._label_font, justify="left",
            background="#ffffcc", relief="solid", bd=1, padx=6, pady=4)
        self.tip_label.pack()

    # -------------------------------------------------------------------- run

    def _run_worker(self):
        self.root.after(0, lambda: self.run_btn.config(state=tk.DISABLED))
        self.root.after(0, lambda: [v.set("—") for v in self.result_vars.values()])
        self.root.after(0, lambda: [lbl.config(foreground="black")
                                    for lbl in self.pnl_labels.values()])
        try:
            df = load_and_compute(
                status_cb=lambda msg: self.root.after(
                    0, lambda m=msg: self.status_var.set(m)))

            self.root.after(0, lambda: self.status_var.set("Fetching ETF highs..."))
            etf_dd = get_etf_drawdowns()
            custom_dd = get_drawdowns(list(self.custom_tickers))

            self.root.after(0, lambda: self.status_var.set("Fetching intraday prices..."))
            intraday = get_intraday_prices()

            summary = df.groupby('Source')['PnL'].sum()
            total = df['PnL'].sum()

            def _update_ui():
                for source, pnl in summary.items():
                    if source in self.result_vars:
                        self.result_vars[source].set(f"${pnl:,.2f}")
                        color = PNL_POS_COLOR if pnl >= 0 else PNL_NEG_COLOR
                        self.pnl_labels[source].config(foreground=color)
                self.result_vars['Total'].set(f"${total:,.2f}")
                self.pnl_labels['Total'].config(
                    foreground=PNL_POS_COLOR if total >= 0 else PNL_NEG_COLOR)
                self._update_etf_table(etf_dd)
                self._update_custom_table(custom_dd)
                self._update_intraday_charts(intraday)
                self.state.plot_df = df
                self._redraw_scatter()
                self.redraw_treemap()
                self.redraw_bar()
                self.redraw_tag_bar()
                ts = datetime.datetime.now().strftime('%H:%M:%S')
                self.status_var.set(f"Done.  Last update: {ts}")

            self.root.after(0, _update_ui)
        except Exception as e:
            traceback.print_exc()
            self.root.after(0, lambda: self.status_var.set(f"Error: {e}"))
        finally:
            self.root.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

    # ----------------------------------------------------------- auto-update

    def toggle_auto(self):
        if not self.state.auto_running:
            self.state.auto_running = True
            self._start_auto_run()
        else:
            self.state.auto_running = False
            self.auto_btn.config(text="Auto Update")
            if self.state.auto_after_id:
                self.root.after_cancel(self.state.auto_after_id)
                self.state.auto_after_id = None
            if self.state.countdown_id:
                self.root.after_cancel(self.state.countdown_id)
                self.state.countdown_id = None

    def _start_auto_run(self):
        if self.state.auto_running:
            threading.Thread(target=self._auto_worker, daemon=True).start()

    def _auto_worker(self):
        self.root.after(0, lambda: self.auto_btn.config(text="Stop"))
        self._run_worker()
        if self.state.auto_running:
            self.state.auto_after_id = self.root.after(
                AUTO_UPDATE_INTERVAL_MS, self._start_auto_run)
            self.root.after(0, lambda: self._start_countdown(AUTO_UPDATE_COUNTDOWN_SECS))

    def _start_countdown(self, secs_left):
        if not self.state.auto_running:
            return
        self.auto_btn.config(text=f"Stop ({secs_left}s)")
        if secs_left > 0:
            self.state.countdown_id = self.root.after(
                1000, lambda: self._start_countdown(secs_left - 1))

    # ------------------------------------------------------------- scatter / toggles

    def _redraw_all(self):
        self._redraw_scatter()
        self.redraw_treemap()
        self._redraw_bars()

    def _redraw_bars(self):
        self.redraw_bar()
        self.redraw_tag_bar()

    # "Group Tickers" drives scatter + ticker bar (tag bar always grouped)
    _toggle_group = _redraw_all

    def _redraw_scatter(self):
        if self.state.plot_df is None:
            return
        self.state.scatter_df = draw_scatter(
            self.ax, self.state.plot_df,
            log_x=self.log_x_var.get(),
            grouped=self.group_scatter_var.get(),
            return_mode=self.return_mode_var.get(),
        )
        self.canvas.draw()

    def _export_scatter_csv(self):
        if self.state.scatter_df is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export scatter data",
        )
        if path:
            self.state.scatter_df.to_csv(path, index=False)

    # -------------------------------------------------------------- treemap

    def redraw_treemap(self):
        if self.state.plot_df is None:
            return
        rects, plot_data = draw_treemap(
            self.ax_treemap, self.state.plot_df,
            grouped=self.group_scatter_var.get())
        self.state.treemap_rects = rects
        self.state.treemap_df = plot_data
        self.treemap_canvas.draw()

    def _on_treemap_resize(self, event):
        if self.state.treemap_resize_id:
            self.root.after_cancel(self.state.treemap_resize_id)
        self.state.treemap_resize_id = self.root.after(150, self.redraw_treemap)

    # -------------------------------------------------------------- bar chart

    def redraw_bar(self):
        if self.state.plot_df is None:
            return
        bar_df = build_bar_df(self.state.plot_df, sort_by_name=self.sort_by_name.get(),
                              grouped=self.group_scatter_var.get(),
                              return_mode=self.return_mode_var.get())
        draw_bar(self.ax_bar, bar_df, return_mode=self.return_mode_var.get())
        self.state.current_bar_df = bar_df

        n = len(bar_df)
        w_px = max(self.bar_canvas_widget.winfo_width(), 100)
        h_px = int(max(BAR_MIN_HEIGHT_INCHES, n * BAR_ROW_HEIGHT_INCHES)
                   * self.ax_bar.figure.dpi)
        self.bar_canvas_widget.config(width=w_px, height=h_px)
        self.bar_scroll_canvas.itemconfigure(self.bar_window_id, width=w_px)
        self.bar_scroll_canvas.configure(scrollregion=(0, 0, w_px, h_px))
        self.bar_canvas.draw()  # re-render when content changes but size is unchanged

    def _on_bar_area_resize(self, event):
        w = event.width
        if self.state.bar_resize_id:
            self.root.after_cancel(self.state.bar_resize_id)
        self.state.bar_resize_id = self.root.after(
            BAR_RESIZE_DEBOUNCE_MS, lambda: self._do_bar_resize(w))

    def _do_bar_resize(self, w):
        if w < 10:
            return
        h_px = int(self.bar_fig.get_figheight() * self.bar_fig.dpi)
        self.bar_canvas_widget.config(width=w, height=h_px)
        self.bar_scroll_canvas.itemconfigure(self.bar_window_id, width=w)
        self.bar_scroll_canvas.configure(scrollregion=(0, 0, w, h_px))

    def _on_bar_mousewheel(self, event):
        self.bar_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # --------------------------------------------------------------- tag bar chart

    def redraw_tag_bar(self):
        if self.state.plot_df is None:
            return
        tag_df = build_tag_bar_df(self.state.plot_df, sort_by_name=self.sort_by_name.get())
        draw_bar(self.ax_tag_bar, tag_df)
        self.state.current_tag_bar_df = tag_df

        n = len(tag_df)
        w_px = max(self.tag_canvas_widget.winfo_width(), 100)
        h_px = int(max(BAR_MIN_HEIGHT_INCHES, n * BAR_ROW_HEIGHT_INCHES)
                   * self.ax_tag_bar.figure.dpi)
        self.tag_canvas_widget.config(width=w_px, height=h_px)
        self.tag_scroll_canvas.itemconfigure(self.tag_window_id, width=w_px)
        self.tag_scroll_canvas.configure(scrollregion=(0, 0, w_px, h_px))
        self.tag_canvas.draw()

    def _on_tag_area_resize(self, event):
        w = event.width
        if self.state.tag_bar_resize_id:
            self.root.after_cancel(self.state.tag_bar_resize_id)
        self.state.tag_bar_resize_id = self.root.after(
            BAR_RESIZE_DEBOUNCE_MS, lambda: self._do_tag_resize(w))

    def _do_tag_resize(self, w):
        if w < 10:
            return
        h_px = int(self.tag_fig.get_figheight() * self.tag_fig.dpi)
        self.tag_canvas_widget.config(width=w, height=h_px)
        self.tag_scroll_canvas.itemconfigure(self.tag_window_id, width=w)
        self.tag_scroll_canvas.configure(scrollregion=(0, 0, w, h_px))

    def _on_tag_mousewheel(self, event):
        self.tag_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # --------------------------------------------------------------- tooltips

    def _show_tooltip(self, text, widget, event):
        self.tip_label.config(text=text)
        rx = widget.winfo_rootx() + int(event.x) + 15
        ry = widget.winfo_rooty() + int(widget.winfo_height() - event.y) - 10
        self.tip_win.geometry(f"+{rx}+{ry}")
        self.tip_win.deiconify()

    def _on_hover(self, event):
        if event.inaxes != self.ax or not self.ax.collections or self.state.scatter_df is None:
            self.tip_win.withdraw()
            return
        for coll in self.ax.collections:
            hit, ind = coll.contains(event)
            if hit:
                i = ind['ind'][0]
                x, y = coll.get_offsets()[i]
                row = self.state.scatter_df.iloc[i]
                ret = self.return_mode_var.get()
                if self.group_scatter_var.get():
                    ticker = row['Ticker Alias']
                    sources_str = row['Sources']
                    per_source = self.state.plot_df[
                        self.state.plot_df['Ticker Alias'] == ticker]
                    symbols_str = ', '.join(sorted(per_source['SYMBOL'].unique()))
                    y_label = f"{y * 100:+.2f}%" if ret else f"${y:,.2f}"
                    lines = [
                        f"Ticker:         {ticker}",
                        f"Symbols:       {symbols_str}",
                        f"Sources:       {sources_str}",
                        f"SOD VALUE:  ${x:,.2f}",
                        f"{'Total Return' if ret else 'Total PnL'}:  {y_label}",
                    ]
                    for _, sr in per_source.iterrows():
                        val = f"{sr['% Move On Day'] * 100:+.2f}%" if ret else f"${sr['PnL']:,.2f}"
                        lines.append(f"  {sr['Source']} {'Return' if ret else 'PnL'}:  {val}")
                    text = '\n'.join(lines)
                else:
                    y_label = f"{y * 100:+.2f}%" if ret else f"${y:,.2f}"
                    text = (f"Ticker:         {row['Ticker Alias']}\n"
                            f"Symbol:        {row['SYMBOL']}\n"
                            f"Source:        {row['Source']}\n"
                            f"SOD VALUE:  ${x:,.2f}\n"
                            f"{'Return' if ret else 'PnL'}:  {y_label}")
                self._show_tooltip(text, self.canvas.get_tk_widget(), event)
                return
        self.tip_win.withdraw()

    def _on_bar_hover(self, event):
        if (event.inaxes != self.ax_bar
                or self.state.current_bar_df is None
                or event.ydata is None):
            self.tip_win.withdraw()
            return
        i = round(event.ydata)
        n = len(self.state.current_bar_df)
        if 0 <= i < n and abs(event.ydata - i) <= 0.4:
            row = self.state.current_bar_df.iloc[i]
            ticker = row['Ticker Alias']
            source = row['Source']  # None when grouped
            if self.state.plot_df is not None:
                mask = self.state.plot_df['Ticker Alias'] == ticker
                if source is not None:
                    mask &= self.state.plot_df['Source'] == source
                matches = self.state.plot_df[mask]
                if not matches.empty:
                    desc = matches.iloc[0]['DESCRIPTION']
                    pct = matches.iloc[0]['% Move On Day']
                    src_label = f" ({source})" if source is not None else ""
                    text = f"{desc}\n{ticker}{src_label}:  {pct * 100:+.2f}%"
                    self._show_tooltip(text, self.bar_canvas.get_tk_widget(), event)
                    return
        self.tip_win.withdraw()

    def _on_treemap_hover(self, event):
        if (event.inaxes != self.ax_treemap
                or not self.state.treemap_rects
                or event.xdata is None):
            self.tip_win.withdraw()
            return
        for i, rect in enumerate(self.state.treemap_rects):
            if (rect['x'] <= event.xdata <= rect['x'] + rect['dx'] and
                    rect['y'] <= event.ydata <= rect['y'] + rect['dy']):
                row = self.state.treemap_df.iloc[i]
                pct = row['pct_move']
                text = (f"Ticker:        {row['Ticker Alias']}\n"
                        f"SOD VALUE: ${row['SOD VALUE']:,.0f}\n"
                        f"PnL:           ${row['PnL']:,.0f}\n"
                        f"Move:         {pct * 100:+.2f}%")
                self._show_tooltip(text, self.treemap_canvas.get_tk_widget(), event)
                return
        self.tip_win.withdraw()

    def _on_tag_bar_hover(self, event):
        if (event.inaxes != self.ax_tag_bar
                or self.state.current_tag_bar_df is None
                or event.ydata is None):
            self.tip_win.withdraw()
            return
        i = round(event.ydata)
        n = len(self.state.current_tag_bar_df)
        if 0 <= i < n and abs(event.ydata - i) <= 0.4:
            row = self.state.current_tag_bar_df.iloc[i]
            tag = row['Tag']
            pnl = row['PnL']
            if self.state.plot_df is not None:
                positions = self.state.plot_df[self.state.plot_df['Tag'] == tag]
                tickers = ', '.join(sorted(positions['Ticker Alias'].unique()))
                symbols = ', '.join(sorted(positions['SYMBOL'].unique()))
                sod = positions['SOD VALUE'].sum()
                text = (f"Tag: {tag}\n"
                        f"SOD VALUE:  ${sod:,.0f}\n"
                        f"PnL: ${pnl:,.0f}\n"
                        f"Tickers: {tickers}\n"
                        f"Symbols: {symbols}")
                self._show_tooltip(text, self.tag_canvas.get_tk_widget(), event)
                return
        self.tip_win.withdraw()

    # ----------------------------------------------------------------- log x

    def _toggle_log_x(self):
        if self.log_x_var.get():
            self.ax.set_xscale('log')
            self.ax.set_xlabel("SOD VALUE ($)  [log scale]")
        else:
            self.ax.set_xscale('linear')
            self.ax.set_xlabel("SOD VALUE ($)")
        self.canvas.draw()
