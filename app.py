import datetime
import json
import os
import threading
from zoneinfo import ZoneInfo

import pandas as pd
import tkinter as tk
from tkinter import font as tkfont, filedialog, ttk

from constants import (
    AUTO_UPDATE_INTERVAL_MS, AUTO_UPDATE_COUNTDOWN_SECS,
    BTN_BG, BTN_BG_ACTIVE, BTN_FG_DISABLED,
    PNL_POS_COLOR, PNL_NEG_COLOR, Col,
)
from data import DEFAULT_TICKERS, INTRADAY_TICKERS, validate_ticker
from charts import build_bar_df, build_tag_bar_df
from drawdown_table import DrawdownTable
from bar_chart_pane import ScrollableBarChart
from intraday_panel import IntradayChartGrid
from scatter_pane import ScatterPane
from treemap_pane import TreemapPane
from tooltip import Tooltip
from run_loop import RunLoop, RunResult

ET_TZ = ZoneInfo("America/New_York")

MAX_CUSTOM_TICKERS = 4
CUSTOM_TICKERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "custom_tickers.json")


def _load_custom_tickers() -> list[str]:
    try:
        with open(CUSTOM_TICKERS_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [str(t).upper() for t in data][:MAX_CUSTOM_TICKERS]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_custom_tickers(tickers) -> None:
    with open(CUSTOM_TICKERS_FILE, "w") as f:
        json.dump(list(tickers), f)


class PnLApp:
    def __init__(self, root: tk.Tk):
        self.root = root

        root.title("PnL Monitor")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        self._label_font = tkfont.Font(family="Segoe UI", size=11)
        self._value_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        self.tooltip = Tooltip(root, self._label_font)
        self.paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # Toggle vars (must exist before panes register callbacks)
        self.log_x_var = tk.BooleanVar(value=True)
        self.group_scatter_var = tk.BooleanVar(value=True)
        self.return_mode_var = tk.BooleanVar(value=False)
        self.sort_by_name = tk.BooleanVar(value=False)

        self._plot_df: pd.DataFrame | None = None

        self._build_controls()
        self._build_panes()
        self._run_loop = RunLoop(
            root,
            interval_ms=AUTO_UPDATE_INTERVAL_MS,
            countdown_secs=AUTO_UPDATE_COUNTDOWN_SECS,
            custom_tickers_provider=self.custom_table.get_tickers,
            on_result=self._on_data_ready,
            on_status=self.status_var.set,
            on_busy=lambda busy: self.run_btn.config(
                state=tk.DISABLED if busy else tk.NORMAL),
            on_auto_label=lambda text: self.auto_btn.config(text=text),
        )
        self._bind_shortcuts()

    # ------------------------------------------------------------------ build

    def _bind_shortcuts(self):
        self.root.bind('<F5>', lambda _e: self._run_loop.run_once())
        self.root.bind('<Control-a>', lambda _e: self._run_loop.toggle_auto())
        self.root.bind('<Control-s>', lambda _e: self._export_scatter_csv())

    def _action_btn(self, parent, text, command, width=12):
        return tk.Button(
            parent, text=text, width=width, command=command,
            font=self._label_font,
            bg=BTN_BG, fg='white',
            activebackground=BTN_BG_ACTIVE, activeforeground='white',
            disabledforeground=BTN_FG_DISABLED,
            relief='raised', bd=3, padx=8, cursor='hand2',
        )

    def _build_controls(self):
        pad = {"padx": 16, "pady": 8}
        ctrl = ttk.Frame(self.root)
        ctrl.grid(row=0, column=0, sticky="ew")
        ctrl.columnconfigure(0, weight=0)
        ctrl.columnconfigure(1, weight=0)
        ctrl.columnconfigure(2, weight=1)

        self.status_var = tk.StringVar(value="Ready.")

        self.etf_table = DrawdownTable(
            ctrl, "ETF % from Highs", list(DEFAULT_TICKERS),
            self._label_font, editable=False,
        )
        self.etf_table.grid(row=0, column=0, rowspan=3, sticky="nw",
                            padx=(8, 16), pady=8)

        self.custom_table = DrawdownTable(
            ctrl, "Custom % from Highs", _load_custom_tickers(),
            self._label_font, editable=True, show_today=True,
            max_tickers=MAX_CUSTOM_TICKERS,
            sibling_height_provider=lambda: self.etf_table.winfo_reqheight(),
            on_change=_save_custom_tickers,
            on_added=lambda _tkr: threading.Thread(
                target=self._refresh_custom_drawdowns, daemon=True).start(),
            validator=validate_ticker,
            root=self.root,
            status_cb=self.status_var.set,
        )
        self.custom_table.grid(row=0, column=1, rowspan=3, sticky="nw",
                               padx=(0, 16), pady=8)

        self.intraday_grid = IntradayChartGrid(ctrl, INTRADAY_TICKERS, ET_TZ)
        self.intraday_grid.grid(row=0, column=3, rowspan=3, sticky="ne",
                                padx=(8, 8), pady=8)

        btn_frame = ttk.Frame(ctrl)
        btn_frame.grid(row=0, column=2, **pad)

        self.run_btn = self._action_btn(
            btn_frame, "Run", width=10,
            command=lambda: self._run_loop.run_once())
        self.run_btn.grid(row=0, column=0, padx=(0, 8))

        self.auto_btn = self._action_btn(
            btn_frame, "Auto Update", width=13,
            command=lambda: self._run_loop.toggle_auto())
        self.auto_btn.grid(row=0, column=1, padx=(8, 16))

        ttk.Separator(btn_frame, orient=tk.VERTICAL).grid(
            row=0, column=2, sticky="ns", padx=(0, 8))

        ttk.Checkbutton(
            btn_frame, text="Log X axis",
            variable=self.log_x_var, command=self._toggle_log_x,
        ).grid(row=0, column=3, padx=(0, 8))

        ttk.Checkbutton(
            btn_frame, text="Group Tickers",
            variable=self.group_scatter_var, command=self._redraw_all,
        ).grid(row=0, column=4, padx=(0, 8))

        ttk.Checkbutton(
            btn_frame, text="Return %",
            variable=self.return_mode_var, command=self._redraw_all,
        ).grid(row=0, column=5, padx=(0, 8))

        ttk.Checkbutton(
            btn_frame, text="Sort A–Z",
            variable=self.sort_by_name, command=self._redraw_bars,
        ).grid(row=0, column=6)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).grid(
            row=0, column=7, sticky="ns", padx=(8, 0))

        self._action_btn(
            btn_frame, "Export CSV", width=12,
            command=self._export_scatter_csv,
        ).grid(row=0, column=8, padx=(8, 0))

        ttk.Label(ctrl, textvariable=self.status_var,
                  foreground="gray").grid(row=1, column=2, **pad)

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

    def _build_panes(self):
        # PanedWindow order: treemap | scatter | ticker bar | tag bar
        self.treemap_pane = TreemapPane(
            self.paned, self.root,
            weight=7,
            hover_text=self._treemap_hover_text,
            tooltip=self.tooltip,
        )
        self.scatter_pane = ScatterPane(
            self.paned,
            weight=9,
            hover_text=self._scatter_hover_text,
            tooltip=self.tooltip,
        )
        self.bar_pane = ScrollableBarChart(
            self.paned, self.root,
            weight=6,
            build_df=lambda df, **opts: build_bar_df(df, **opts),
            hover_text=self._bar_hover_text,
            tooltip=self.tooltip,
        )
        self.tag_bar_pane = ScrollableBarChart(
            self.paned, self.root,
            weight=7,
            build_df=lambda df, **opts: build_tag_bar_df(
                df, sort_by_name=opts.get('sort_by_name', False)),
            hover_text=self._tag_bar_hover_text,
            tooltip=self.tooltip,
        )

    # -------------------------------------------------------------- callbacks

    def _refresh_custom_drawdowns(self):
        from data import get_drawdowns  # localized import to avoid top-level cycles if any
        tickers = self.custom_table.get_tickers()
        if not tickers:
            return
        dd = get_drawdowns(tickers)
        self.root.after(0, lambda: self.custom_table.update_values(dd))

    def _on_data_ready(self, result: RunResult):
        self._plot_df = result.plot_df
        for v in self.result_vars.values():
            v.set("—")
        for lbl in self.pnl_labels.values():
            lbl.config(foreground="black")

        summary = result.plot_df.groupby(Col.SOURCE)[Col.PNL].sum()
        total = result.plot_df[Col.PNL].sum()
        for source, pnl in summary.items():
            if source in self.result_vars:
                self.result_vars[source].set(f"${pnl:,.2f}")
                color = PNL_POS_COLOR if pnl >= 0 else PNL_NEG_COLOR
                self.pnl_labels[source].config(foreground=color)
        self.result_vars['Total'].set(f"${total:,.2f}")
        self.pnl_labels['Total'].config(
            foreground=PNL_POS_COLOR if total >= 0 else PNL_NEG_COLOR)

        self.etf_table.update_values(result.etf_dd)
        self.custom_table.update_values(result.custom_dd)
        self.intraday_grid.update(result.intraday)

        self._redraw_all()
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self.status_var.set(f"Done.  Last update: {ts}")

    # ------------------------------------------------------------- redraws

    def _redraw_all(self):
        self.scatter_pane.redraw(
            self._plot_df,
            log_x=self.log_x_var.get(),
            grouped=self.group_scatter_var.get(),
            return_mode=self.return_mode_var.get(),
        )
        self.treemap_pane.redraw(
            self._plot_df, grouped=self.group_scatter_var.get())
        self._redraw_bars()

    def _redraw_bars(self):
        if self._plot_df is None:
            return
        self.bar_pane.redraw(
            self._plot_df,
            sort_by_name=self.sort_by_name.get(),
            grouped=self.group_scatter_var.get(),
            return_mode=self.return_mode_var.get(),
        )
        self.tag_bar_pane.redraw(
            self._plot_df,
            sort_by_name=self.sort_by_name.get(),
        )

    def _toggle_log_x(self):
        self.scatter_pane.toggle_log_x(self.log_x_var.get())

    def _export_scatter_csv(self):
        df = self.scatter_pane.scatter_df
        if df is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export scatter data",
        )
        if path:
            df.to_csv(path, index=False)

    # -------------------------------------------------------------- hover text

    def _scatter_hover_text(self, row, x, y, ret, grouped, plot_df):
        if grouped:
            ticker = row[Col.TICKER]
            sources_str = row['Sources']
            per_source = plot_df[plot_df[Col.TICKER] == ticker]
            symbols_str = ', '.join(sorted(per_source[Col.SYMBOL].unique()))
            y_label = f"{y * 100:+.2f}%" if ret else f"${y:,.2f}"
            lines = [
                f"Ticker:         {ticker}",
                f"Symbols:       {symbols_str}",
                f"Sources:       {sources_str}",
                f"SOD VALUE:  ${x:,.2f}",
                f"{'Total Return' if ret else 'Total PnL'}:  {y_label}",
            ]
            for _, sr in per_source.iterrows():
                val = f"{sr[Col.PCT_MOVE] * 100:+.2f}%" if ret else f"${sr[Col.PNL]:,.2f}"
                lines.append(f"  {sr[Col.SOURCE]} {'Return' if ret else 'PnL'}:  {val}")
            return '\n'.join(lines)
        y_label = f"{y * 100:+.2f}%" if ret else f"${y:,.2f}"
        return (f"Ticker:         {row[Col.TICKER]}\n"
                f"Symbol:        {row[Col.SYMBOL]}\n"
                f"Source:        {row[Col.SOURCE]}\n"
                f"SOD VALUE:  ${x:,.2f}\n"
                f"{'Return' if ret else 'PnL'}:  {y_label}")

    def _bar_hover_text(self, row, plot_df):
        ticker = row[Col.TICKER]
        source = row[Col.SOURCE]  # None when grouped
        mask = plot_df[Col.TICKER] == ticker
        if source is not None:
            mask &= plot_df[Col.SOURCE] == source
        matches = plot_df[mask]
        if matches.empty:
            return None
        desc = matches.iloc[0][Col.DESCRIPTION]
        pct = matches.iloc[0][Col.PCT_MOVE]
        src_label = f" ({source})" if source is not None else ""
        return f"{desc}\n{ticker}{src_label}:  {pct * 100:+.2f}%"

    def _tag_bar_hover_text(self, row, plot_df):
        tag = row[Col.TAG]
        pnl = row[Col.PNL]
        positions = plot_df[plot_df[Col.TAG] == tag]
        if positions.empty:
            return None
        tickers = ', '.join(sorted(positions[Col.TICKER].unique()))
        symbols = ', '.join(sorted(positions[Col.SYMBOL].unique()))
        sod = positions[Col.SOD_VALUE].sum()
        return (f"Tag: {tag}\n"
                f"SOD VALUE:  ${sod:,.0f}\n"
                f"PnL: ${pnl:,.0f}\n"
                f"Tickers: {tickers}\n"
                f"Symbols: {symbols}")

    def _treemap_hover_text(self, row, _rect):
        pct = row['pct_move']
        return (f"Ticker:        {row[Col.TICKER]}\n"
                f"SOD VALUE: ${row[Col.SOD_VALUE]:,.0f}\n"
                f"PnL:           ${row[Col.PNL]:,.0f}\n"
                f"Move:         {pct * 100:+.2f}%")
