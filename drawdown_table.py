import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from constants import (
    BTN_BG, BTN_BG_ACTIVE, DELETE_FG, PNL_POS_COLOR, PNL_NEG_COLOR,
)


class DrawdownTable(ttk.LabelFrame):
    """3-column table showing % from 6W and All-Time highs for a list of tickers.

    Two modes:
      * editable=False: fixed ticker list (e.g. SPY/QQQ/IWM/EEM benchmarks).
      * editable=True:  × delete labels and an Add Entry+Button row. Height is
        pinned to a sibling table via `sibling_height_provider` so both align.
    """

    def __init__(
        self,
        parent,
        title: str,
        tickers: list[str],
        label_font,
        *,
        editable: bool = False,
        show_today: bool = False,
        max_tickers: int = 4,
        sibling_height_provider: Callable[[], int] | None = None,
        on_change: Callable[[list[str]], None] | None = None,
        on_added: Callable[[str], None] | None = None,
        validator: Callable[[str], bool] | None = None,
        root: tk.Tk | None = None,
        status_cb: Callable[[str], None] | None = None,
    ):
        super().__init__(parent, text=title, padding=(8, 6))
        self._tickers = list(tickers)
        self._label_font = label_font
        self._editable = editable
        self._max_tickers = max_tickers
        self._sibling_height = sibling_height_provider
        self._on_change = on_change
        self._on_added = on_added
        self._validator = validator
        self._root = root
        self._status_cb = status_cb

        value_cols: list[tuple[str, str]] = []
        if show_today:
            value_cols.append(("Today", "Today"))
        value_cols.extend([("6W", "6W High"), ("ATH", "All-Time High")])
        self._value_cols = tuple(value_cols)

        self._vars: dict[tuple[str, str], tk.StringVar] = {}
        self._labels: dict[tuple[str, str], ttk.Label] = {}
        self._entry_var = tk.StringVar()

        self._render()

    # -- public API ----------------------------------------------------------

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def update_values(self, dd: dict[str, dict[str, float | None]]) -> None:
        for tkr, vals in dd.items():
            for key, _header in self._value_cols:
                v = self._vars.get((tkr, key))
                lbl = self._labels.get((tkr, key))
                if v is None or lbl is None:
                    continue
                val = vals.get(key)
                if val is None:
                    v.set("—")
                    lbl.config(foreground="gray")
                else:
                    v.set(f"{val * 100:+.2f}%")
                    lbl.config(foreground=PNL_NEG_COLOR if val < 0 else PNL_POS_COLOR)

    # -- internal rendering --------------------------------------------------

    def _render(self):
        for w in self.winfo_children():
            w.destroy()
        self._vars = {}
        self._labels = {}

        ttk.Label(self, text="Ticker", font=self._label_font,
                  anchor="center").grid(row=0, column=0, padx=8, pady=2)
        for col, (_key, header) in enumerate(self._value_cols, start=1):
            ttk.Label(self, text=header, font=self._label_font,
                      anchor="center").grid(row=0, column=col, padx=8, pady=2)

        delete_col = len(self._value_cols) + 1

        for i, tkr in enumerate(self._tickers, start=1):
            ttk.Label(self, text=tkr, font=self._label_font,
                      anchor="center").grid(row=i, column=0, padx=8, pady=2)
            for col, (key, _header) in enumerate(self._value_cols, start=1):
                v = tk.StringVar(value="—")
                lbl = ttk.Label(self, textvariable=v, font=self._label_font,
                                anchor="e", width=8)
                lbl.grid(row=i, column=col, padx=8, pady=2)
                self._vars[(tkr, key)] = v
                self._labels[(tkr, key)] = lbl
            if self._editable:
                del_lbl = ttk.Label(self, text="×", font=self._label_font,
                                    foreground=DELETE_FG, cursor='hand2',
                                    anchor='center', width=2)
                del_lbl.grid(row=i, column=delete_col, padx=(2, 4), pady=2)
                del_lbl.bind("<Button-1>",
                             lambda _e, t=tkr: self._remove(t))

        last_row = len(self._tickers)

        if self._editable and len(self._tickers) < self._max_tickers:
            add_row = last_row + 1
            self._entry_var.set("")
            entry = ttk.Entry(self, textvariable=self._entry_var,
                              width=8, font=self._label_font)
            entry.grid(row=add_row, column=0, padx=8, pady=2, sticky="ew")
            entry.bind("<Return>", lambda _e: self._add_clicked())
            tk.Button(
                self, text="Add", width=5,
                command=self._add_clicked, font=self._label_font,
                bg=BTN_BG, fg='white',
                activebackground=BTN_BG_ACTIVE, activeforeground='white',
                relief='raised', bd=2, cursor='hand2',
            ).grid(row=add_row, column=1, columnspan=delete_col,
                   padx=4, pady=2, sticky="w")
            last_row = add_row

        if self._editable:
            for filler_row in range(last_row + 1, self._max_tickers + 1):
                ttk.Label(self, text=" ", font=self._label_font,
                          anchor="center").grid(row=filler_row, column=0,
                                                padx=8, pady=2)
            if self._sibling_height and self._root:
                self._root.after_idle(self._sync_height)

    def _sync_height(self):
        self.grid_propagate(True)
        self.update_idletasks()
        natural_w = self.winfo_reqwidth()
        target_h = self._sibling_height()
        self.config(width=natural_w, height=target_h)
        self.grid_propagate(False)

    # -- add/remove logic ----------------------------------------------------

    def _add_clicked(self):
        tkr = self._entry_var.get().strip().upper()
        if not tkr:
            return
        if tkr in self._tickers:
            if self._status_cb:
                self._status_cb(f"{tkr} already in custom list")
            return
        if len(self._tickers) >= self._max_tickers:
            return
        if self._status_cb:
            self._status_cb(f"Validating {tkr}...")
        threading.Thread(target=self._add_worker, args=(tkr,),
                         daemon=True).start()

    def _add_worker(self, tkr: str):
        valid = self._validator(tkr) if self._validator else True

        def _finish():
            if not valid:
                if self._status_cb:
                    self._status_cb(f"Invalid ticker: {tkr}")
                return
            if tkr in self._tickers or len(self._tickers) >= self._max_tickers:
                return
            self._tickers.append(tkr)
            if self._on_change:
                self._on_change(list(self._tickers))
            self._render()
            if self._status_cb:
                self._status_cb(f"Added {tkr}")
            if self._on_added:
                self._on_added(tkr)

        if self._root:
            self._root.after(0, _finish)
        else:
            _finish()

    def _remove(self, tkr: str):
        if tkr in self._tickers:
            self._tickers.remove(tkr)
            if self._on_change:
                self._on_change(list(self._tickers))
            self._render()
