import datetime
import threading
import traceback
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import tkinter as tk
from tkinter import font as tkfont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from constants import (
    AUTO_UPDATE_INTERVAL_MS, AUTO_UPDATE_COUNTDOWN_SECS,
    BAR_ROW_HEIGHT_INCHES, BAR_MIN_HEIGHT_INCHES, BAR_RESIZE_DEBOUNCE_MS,
    PNL_POS_COLOR, PNL_NEG_COLOR,
)
from data import load_and_compute
from charts import draw_scatter, build_bar_df, draw_bar


@dataclass
class AppState:
    plot_df: Optional[pd.DataFrame] = None      # full per-position DataFrame
    scatter_df: Optional[pd.DataFrame] = None   # what's currently plotted (may be grouped)
    current_bar_df: Optional[pd.DataFrame] = None
    auto_running: bool = False
    auto_after_id: Optional[str] = None
    countdown_id: Optional[str] = None
    bar_resize_id: Optional[str] = None


class PnLApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state = AppState()

        root.title("PnL Monitor")
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        self._label_font = tkfont.Font(family="Segoe UI", size=11)
        self._value_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        self._build_controls()
        self._build_scatter()
        self._build_bar()
        self._build_tooltip()

    # ------------------------------------------------------------------ build

    def _build_controls(self):
        pad = {"padx": 16, "pady": 8}
        ctrl = tk.Frame(self.root)
        ctrl.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctrl.columnconfigure((0, 1, 2), weight=1)

        btn_frame = tk.Frame(ctrl)
        btn_frame.grid(row=0, column=0, columnspan=3, **pad)

        self.run_btn = tk.Button(
            btn_frame, text="Run", font=self._label_font, width=12,
            command=lambda: threading.Thread(
                target=self._run_worker, daemon=True).start()
        )
        self.run_btn.grid(row=0, column=0, padx=(0, 8))

        self.auto_btn = tk.Button(
            btn_frame, text="Auto Update", font=self._label_font, width=12,
            command=self.toggle_auto
        )
        self.auto_btn.grid(row=0, column=1, padx=(8, 16))

        self.log_x_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            btn_frame, text="Log X axis", font=self._label_font,
            variable=self.log_x_var, command=self._toggle_log_x
        ).grid(row=0, column=2, padx=(0, 8))

        self.group_scatter_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            btn_frame, text="Group Tickers", font=self._label_font,
            variable=self.group_scatter_var, command=self._toggle_group
        ).grid(row=0, column=3, padx=(0, 8))

        self.return_mode_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            btn_frame, text="Return %", font=self._label_font,
            variable=self.return_mode_var, command=self._redraw_all
        ).grid(row=0, column=4, padx=(0, 8))

        self.sort_by_name = tk.BooleanVar(value=False)
        tk.Checkbutton(
            btn_frame, text="Sort A–Z", font=self._label_font,
            variable=self.sort_by_name, command=self.redraw_bar
        ).grid(row=0, column=5)

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(ctrl, textvariable=self.status_var, font=self._label_font, fg="gray").grid(
            row=1, column=0, columnspan=3, **pad)

        self.result_vars = {
            "UBS": tk.StringVar(value="—"),
            "401K": tk.StringVar(value="—"),
            "Total": tk.StringVar(value="—"),
        }

        fields = tk.Frame(ctrl, relief="groove", bd=2, padx=12, pady=8)
        fields.grid(row=2, column=0, columnspan=3, pady=(4, 12))

        self.pnl_labels = {}
        for col, (label_text, key) in enumerate(
                [("UBS PnL", "UBS"), ("401K PnL", "401K"), ("Total PnL", "Total")]):
            tk.Label(fields, text=label_text, font=self._label_font, anchor="center").grid(
                row=0, column=col, padx=20, pady=(6, 2))
            lbl = tk.Label(fields, textvariable=self.result_vars[key],
                           font=self._value_font, width=12, anchor="center")
            lbl.grid(row=1, column=col, padx=20, pady=(0, 6))
            self.pnl_labels[key] = lbl

    def _build_scatter(self):
        self.fig, self.ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
        self.ax.set_facecolor("#f8f8f8")
        self.ax.set_xlabel("SOD VALUE ($)")
        self.ax.set_ylabel("PnL ($)")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().grid(
            row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 16))
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_hover)

    def _build_bar(self):
        bar_outer = tk.Frame(self.root)
        bar_outer.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 16))
        bar_outer.rowconfigure(0, weight=1)
        bar_outer.columnconfigure(0, weight=1)

        self.bar_scroll_canvas = tk.Canvas(bar_outer, highlightthickness=0)
        bar_scrollbar = tk.Scrollbar(
            bar_outer, orient="vertical", command=self.bar_scroll_canvas.yview)
        self.bar_scroll_canvas.configure(yscrollcommand=bar_scrollbar.set)
        bar_scrollbar.grid(row=0, column=1, sticky="ns")
        self.bar_scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self.bar_fig, self.ax_bar = plt.subplots(figsize=(4, 6), constrained_layout=True)
        self.ax_bar.set_facecolor("#f8f8f8")
        self.ax_bar.set_xlabel("PnL ($)")

        self.bar_canvas = FigureCanvasTkAgg(self.bar_fig, master=self.bar_scroll_canvas)
        self.bar_canvas_widget = self.bar_canvas.get_tk_widget()
        self.bar_window_id = self.bar_scroll_canvas.create_window(
            0, 0, anchor="nw", window=self.bar_canvas_widget)

        self.bar_scroll_canvas.bind("<Configure>", self._on_bar_area_resize)
        self.bar_scroll_canvas.bind("<MouseWheel>", self._on_bar_mousewheel)
        self.bar_canvas_widget.bind("<MouseWheel>", self._on_bar_mousewheel)
        self.bar_fig.canvas.mpl_connect('motion_notify_event', self._on_bar_hover)

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
        self.root.after(0, lambda: [lbl.config(fg="black")
                                    for lbl in self.pnl_labels.values()])
        try:
            df = load_and_compute(
                status_cb=lambda msg: self.root.after(
                    0, lambda m=msg: self.status_var.set(m)))

            summary = df.groupby('Source')['PnL'].sum()
            total = df['PnL'].sum()

            def _update_ui():
                for source, pnl in summary.items():
                    if source in self.result_vars:
                        self.result_vars[source].set(f"${pnl:,.2f}")
                        color = PNL_POS_COLOR if pnl >= 0 else PNL_NEG_COLOR
                        self.pnl_labels[source].config(fg=color)
                self.result_vars['Total'].set(f"${total:,.2f}")
                self.pnl_labels['Total'].config(
                    fg=PNL_POS_COLOR if total >= 0 else PNL_NEG_COLOR)
                self.state.plot_df = df
                self._redraw_scatter()
                self.redraw_bar()
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
        self.redraw_bar()

    # "Group Tickers" drives both charts
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
                    y_label = f"{y * 100:+.2f}%" if ret else f"${y:,.2f}"
                    lines = [
                        f"Ticker:         {ticker}",
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
                    text = (f"Source:        {row['Source']}\n"
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

    # ----------------------------------------------------------------- log x

    def _toggle_log_x(self):
        if self.log_x_var.get():
            self.ax.set_xscale('log')
            self.ax.set_xlabel("SOD VALUE ($)  [log scale]")
        else:
            self.ax.set_xscale('linear')
            self.ax.set_xlabel("SOD VALUE ($)")
        self.canvas.draw()
