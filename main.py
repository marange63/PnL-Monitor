from claudedev_shared import ubs_live_price_holdings, ubs_401k_holdings
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import font as tkfont
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def get_price_data(ticker):
    try:
        data = yf.Ticker(ticker).fast_info
        last_price = data.last_price
        last_close = data.regular_market_previous_close
        pct_move = (last_price - last_close) / last_close
        return last_price, last_close, pct_move
    except Exception as e:
        print(f"Warning: failed to get price for {ticker}: {e}")
        return None, None, None


def run_pnl(status_var, result_vars, run_btn,
            ax, canvas, ax_bar, bar_canvas, bar_scroll_canvas, plot_df):
    run_btn.config(state=tk.DISABLED)
    for var in result_vars.values():
        var.set("—")

    try:
        status_var.set("Loading holdings...")
        df = ubs_live_price_holdings()
        df2 = ubs_401k_holdings()
        df = pd.concat([df, df2], ignore_index=True)

        status_var.set("Getting prices...")
        tickers = df['Ticker Alias'].tolist()
        with ThreadPoolExecutor() as executor:
            results = dict(zip(tickers, executor.map(get_price_data, tickers)))
        df[['Last Price', 'Last Close', '% Move On Day']] = df['Ticker Alias'].map(results).apply(pd.Series)

        status_var.set("Calculating PnL...")
        df['PnL'] = df['SOD VALUE'] * df['% Move On Day']

        summary = df.groupby('Source')['PnL'].sum()
        for source, pnl in summary.items():
            if source in result_vars:
                result_vars[source].set(f"${pnl:,.2f}")
        result_vars['Total'].set(f"${df['PnL'].sum():,.2f}")
        plot_df[0] = df.reset_index(drop=True)

        # Scatter plot
        ax.clear()
        colors = df['Source'].map({"UBS": "#1f77b4", "401K": "#ff7f0e"})
        ax.scatter(df['SOD VALUE'], df['PnL'], c=colors, alpha=0.7, edgecolors='white', linewidths=0.5)
        for _, row in df.iterrows():
            ax.annotate(row['Ticker Alias'], (row['SOD VALUE'], row['PnL']),
                        fontsize=7, textcoords="offset points", xytext=(4, 4))
        ax.axhline(0, color='gray', linewidth=0.8, linestyle='--')
        ax.set_xlabel("SOD VALUE ($)")
        ax.set_ylabel("PnL ($)")
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"${y:,.0f}"))
        ax.xaxis.set_major_locator(plt.MaxNLocator(nbins=6, prune='both'))
        canvas.draw()

        # Bar chart
        bar_df = df[['Ticker Alias', 'PnL']].dropna().groupby('Ticker Alias', as_index=False)['PnL'].sum()
        bar_df = bar_df.sort_values('PnL', key=abs, ascending=True)
        bar_colors = ['#d62728' if p < 0 else '#2ca02c' for p in bar_df['PnL']]

        ax_bar.clear()
        ax_bar.barh(bar_df['Ticker Alias'], bar_df['PnL'], color=bar_colors,
                    edgecolor='black', linewidth=0.5)
        ax_bar.axvline(0, color='gray', linewidth=0.8, linestyle='--')
        ax_bar.set_xlabel("PnL ($)")
        ax_bar.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax_bar.xaxis.set_major_locator(plt.MaxNLocator(nbins=4, prune='both'))
        ax_bar.set_facecolor("#f8f8f8")
        ax_bar.margins(y=0.01, x=0.18)

        for bar, pnl in zip(ax_bar.patches, bar_df['PnL']):
            w = bar.get_width()
            y = bar.get_y() + bar.get_height() / 2
            if w >= 0:
                ax_bar.annotate(f"${w:,.0f}", xy=(w, y),
                                xytext=(4, 0), textcoords="offset points",
                                va='center', ha='left', fontsize=7)
            else:
                ax_bar.annotate(f"${w:,.0f}", xy=(w, y),
                                xytext=(-4, 0), textcoords="offset points",
                                va='center', ha='right', fontsize=7)

        # Resize bar widget to fit all tickers; width stays at current panel width
        n = len(bar_df)
        bar_cw = bar_canvas.get_tk_widget()
        w_px = max(bar_cw.winfo_width(), 100)
        h_px = int(max(3, n * 0.28) * ax_bar.figure.dpi)
        bar_cw.config(width=w_px, height=h_px)
        bar_scroll_canvas.itemconfigure(bar_window_id, width=w_px)
        bar_scroll_canvas.configure(scrollregion=(0, 0, w_px, h_px))

        status_var.set("Done.")
    except Exception as e:
        status_var.set(f"Error: {e}")
    finally:
        run_btn.config(state=tk.NORMAL)


if __name__ == '__main__':
    root = tk.Tk()
    root.title("PnL Monitor")
    root.columnconfigure(0, weight=3)
    root.columnconfigure(1, weight=2)
    root.rowconfigure(1, weight=1)

    pad = {"padx": 16, "pady": 8}
    label_font = tkfont.Font(family="Segoe UI", size=11)
    value_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

    # Top controls — spans both columns
    ctrl_frame = tk.Frame(root)
    ctrl_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
    ctrl_frame.columnconfigure((0, 1, 2), weight=1)

    plot_df = [None]

    # Auto-update state
    auto_after_id = [None]
    auto_running = [False]
    countdown_id = [None]

    def start_countdown(secs_left):
        if not auto_running[0]:
            return
        auto_btn.config(text=f"Stop ({secs_left}s)")
        if secs_left > 0:
            countdown_id[0] = root.after(1000, lambda: start_countdown(secs_left - 1))

    def start_auto_run():
        if not auto_running[0]:
            return
        threading.Thread(target=_auto_worker, daemon=True).start()

    def _auto_worker():
        root.after(0, lambda: auto_btn.config(text="Stop"))
        run_pnl(status_var, result_vars, run_btn,
                ax, canvas, ax_bar, bar_canvas, bar_scroll_canvas, plot_df)
        if auto_running[0]:
            auto_after_id[0] = root.after(60000, start_auto_run)
            root.after(0, lambda: start_countdown(59))

    def toggle_auto():
        if not auto_running[0]:
            auto_running[0] = True
            start_auto_run()
        else:
            auto_running[0] = False
            auto_btn.config(text="Auto Update")
            if auto_after_id[0]:
                root.after_cancel(auto_after_id[0])
                auto_after_id[0] = None
            if countdown_id[0]:
                root.after_cancel(countdown_id[0])
                countdown_id[0] = None

    btn_frame = tk.Frame(ctrl_frame)
    btn_frame.grid(row=0, column=0, columnspan=3, **pad)

    run_btn = tk.Button(btn_frame, text="Run", font=label_font, width=12,
                        command=lambda: threading.Thread(
                            target=run_pnl,
                            args=(status_var, result_vars, run_btn,
                                  ax, canvas, ax_bar, bar_canvas, bar_scroll_canvas, plot_df),
                            daemon=True
                        ).start())
    run_btn.grid(row=0, column=0, padx=(0, 8))

    auto_btn = tk.Button(btn_frame, text="Auto Update", font=label_font, width=12,
                         command=toggle_auto)
    auto_btn.grid(row=0, column=1, padx=(8, 16))

    log_x_var = tk.BooleanVar(value=False)

    def toggle_log_x():
        if log_x_var.get():
            ax.set_xscale('log')
            ax.set_xlabel("SOD VALUE ($)  [log scale]")
        else:
            ax.set_xscale('linear')
            ax.set_xlabel("SOD VALUE ($)")
        canvas.draw()

    tk.Checkbutton(btn_frame, text="Log X axis", font=label_font,
                   variable=log_x_var, command=toggle_log_x).grid(row=0, column=2)

    status_var = tk.StringVar(value="Ready.")
    tk.Label(ctrl_frame, textvariable=status_var, font=label_font, fg="gray").grid(
        row=1, column=0, columnspan=3, **pad)

    result_vars = {"UBS": tk.StringVar(value="—"),
                   "401K": tk.StringVar(value="—"),
                   "Total": tk.StringVar(value="—")}

    fields_frame = tk.Frame(ctrl_frame, relief="groove", bd=2, padx=12, pady=8)
    fields_frame.grid(row=2, column=0, columnspan=3, pady=(4, 12))

    labels = [("UBS PnL", "UBS"), ("401K PnL", "401K"), ("Total PnL", "Total")]
    for col, (label_text, key) in enumerate(labels):
        tk.Label(fields_frame, text=label_text, font=label_font, anchor="center").grid(
            row=0, column=col, padx=20, pady=(6, 2))
        tk.Label(fields_frame, textvariable=result_vars[key], font=value_font, width=12, anchor="center").grid(
            row=1, column=col, padx=20, pady=(0, 6))

    # Left: scatter plot
    fig, ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
    ax.set_facecolor("#f8f8f8")
    ax.set_xlabel("SOD VALUE ($)")
    ax.set_ylabel("PnL ($)")

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 16))

    # Right: scrollable bar chart
    bar_outer = tk.Frame(root)
    bar_outer.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 16))
    bar_outer.rowconfigure(0, weight=1)
    bar_outer.columnconfigure(0, weight=1)

    bar_scroll_canvas = tk.Canvas(bar_outer, highlightthickness=0)
    bar_scrollbar = tk.Scrollbar(bar_outer, orient="vertical", command=bar_scroll_canvas.yview)
    bar_scroll_canvas.configure(yscrollcommand=bar_scrollbar.set)
    bar_scrollbar.grid(row=0, column=1, sticky="ns")
    bar_scroll_canvas.grid(row=0, column=0, sticky="nsew")

    bar_fig, ax_bar = plt.subplots(figsize=(4, 6), constrained_layout=True)
    ax_bar.set_facecolor("#f8f8f8")
    ax_bar.set_xlabel("PnL ($)")

    bar_canvas = FigureCanvasTkAgg(bar_fig, master=bar_scroll_canvas)
    bar_canvas_widget = bar_canvas.get_tk_widget()
    bar_window_id = bar_scroll_canvas.create_window(0, 0, anchor="nw", window=bar_canvas_widget)

    _bar_resize_id = [None]

    def on_bar_area_resize(event):
        w = event.width
        if _bar_resize_id[0]:
            root.after_cancel(_bar_resize_id[0])
        _bar_resize_id[0] = root.after(50, lambda: _do_bar_resize(w))

    def _do_bar_resize(w):
        if w < 10:
            return
        h_px = int(bar_fig.get_figheight() * bar_fig.dpi)
        # Config the widget — this triggers matplotlib's own <Configure>/resize()
        # handler which recreates _tkphoto at the right size and redraws
        bar_canvas_widget.config(width=w, height=h_px)
        bar_scroll_canvas.itemconfigure(bar_window_id, width=w)
        bar_scroll_canvas.configure(scrollregion=(0, 0, w, h_px))

    bar_scroll_canvas.bind("<Configure>", on_bar_area_resize)

    # Mousewheel scrolling on bar chart
    def on_bar_mousewheel(event):
        bar_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    bar_scroll_canvas.bind("<MouseWheel>", on_bar_mousewheel)
    bar_canvas_widget.bind("<MouseWheel>", on_bar_mousewheel)

    # Hover tooltip on scatter plot
    tip_win = tk.Toplevel(root)
    tip_win.wm_overrideredirect(True)
    tip_win.withdraw()
    tip_label = tk.Label(tip_win, font=label_font, justify="left",
                         background="#ffffcc", relief="solid", bd=1, padx=6, pady=4)
    tip_label.pack()

    def on_hover(event):
        if event.inaxes != ax or not ax.collections:
            tip_win.withdraw()
            return
        for coll in ax.collections:
            hit, ind = coll.contains(event)
            if hit:
                i = ind['ind'][0]
                x, y = coll.get_offsets()[i]
                source = plot_df[0].iloc[i]['Source'] if plot_df[0] is not None else ""
                tip_label.config(text=f"Source:        {source}\nSOD VALUE:  ${x:,.2f}\nPnL:              ${y:,.2f}")
                widget = canvas.get_tk_widget()
                rx = widget.winfo_rootx() + int(event.x) + 15
                ry = widget.winfo_rooty() + int(widget.winfo_height() - event.y) - 10
                tip_win.geometry(f"+{rx}+{ry}")
                tip_win.deiconify()
                return
        tip_win.withdraw()

    fig.canvas.mpl_connect('motion_notify_event', on_hover)

    root.mainloop()