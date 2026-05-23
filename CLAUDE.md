# PnL-Monitor

## Project Overview
Daily portfolio PnL monitor covering a UBS brokerage account and a UBS 401k account. Pulls live holdings from `claudedev_shared`, enriches with real-time Yahoo Finance prices, computes intraday P&L per position and in aggregate, and displays everything in a tkinter GUI with live charts.

## Environment
- **Conda env:** `PnL-Monitor` (`C:\Users\wamfo\anaconda3\envs\PnL-Monitor`) — always use this, not system Python
- **Python interpreter:** `C:\Users\wamfo\anaconda3\envs\PnL-Monitor\python.exe`
- **IDE:** PyCharm
- **GitHub:** https://github.com/marange63/PnL-Monitor (branch: `main`)
- **Deps:** `environment.yml` (Python 3.13) — `claudedev_shared`, `yfinance>=1.2.0`, `pandas>=2.3.0`, `matplotlib>=3.10.0`, `squarify>=0.4.3`, `sv-ttk>=2.6.0`
- **Launchers:** `main.py` (entry point: sets `sv_ttk` light theme, instantiates `PnLApp`); `Launch PnL Monitor.bat` for double-click launch from Explorer (uses env's `pythonw.exe` — no console). User-facing docs in `MANUAL.md`.

## Data Sources
- `ubs_live_price_holdings()` / `ubs_401k_holdings()` — from `claudedev_shared`; both return a DataFrame with `DESCRIPTION`, `SYMBOL`, `SOD VALUE`, `Ticker Alias`, `Tag`, `Source`
- yfinance `fast_info`: use `last_price` and `regular_market_previous_close` (**not** `previous_close`, which includes after-hours)
- Price fetches run concurrently via `ThreadPoolExecutor(max_workers=5)` with a single retry on exception (0.5 s backoff); failed tickers yield `(None, None, None)`.
- **Stock-split auto-detection** (`_detect_split_ratio` in `data.py`): if `last_price / last_close < 0.35`, treats it as a split and divides `last_close` by `round(1/ratio)` before computing `% Move On Day`. Prints a notice when applied.

## DataFrame Columns (computed in `data.py`)
| Column | Description |
|---|---|
| `DESCRIPTION` | Security full name |
| `SYMBOL` | Brokerage symbol |
| `SOD VALUE` | Start-of-day USD value |
| `Ticker Alias` | Yahoo Finance ticker |
| `Source` | `"UBS"` or `"401K"` |
| `Tag` | Sector/category tag; used by tag bar chart |
| `Last Price` | Current price from yfinance |
| `Last Close` | `regular_market_previous_close` |
| `% Move On Day` | `(Last Price - Last Close) / Last Close` — decimal, e.g. 0.0179 = 1.79% |
| `PnL` | `SOD VALUE * % Move On Day` |

## Module Structure
| File | Contents |
|---|---|
| `constants.py` | Named constants: colors, intervals, sizing |
| `data.py` | `get_price_data(ticker)`, `load_and_compute(status_cb)`, `get_etf_drawdowns()`, `get_drawdowns(tickers)`, `validate_ticker(ticker)`, `get_intraday_prices()` |
| `charts.py` | `draw_scatter`, `draw_bar`, `draw_treemap`, `build_grouped_scatter_df`, `build_bar_df`, `build_tag_bar_df`, `dollar_fmt`, `pct_fmt` |
| `app.py` | `AppState` dataclass, `PnLApp` class (controls, four chart panes, tooltips, auto-update loop) |
| `main.py` | Entry point — `Tk()` + `sv_ttk.set_theme("light")` + `PnLApp(root)` |

## GUI Layout

### Top control strip
Run · Auto Update (60 s loop; button relabels to `Stop (Ns)` with live countdown) · Log X axis · Group Tickers · Return % · Sort A–Z · Export CSV · status label · PnL summary (UBS / 401K / Total — values color-coded green/red).
Three intraday thumbnail charts for SPY, QQQ, and IWM sit to the right of the buttons (1-min bars, `period="1d"`). Y-axis is **% return vs previous close** with a shared y-range across both charts; line is drawn as a `LineCollection` so each segment is colored green or red by the sign of its midpoint; dotted gray line marks 0%; title shows ticker + current % move, colored by sign of latest value.

The **ETF % from Highs** table sits in column 0, with the **Custom % from Highs** table immediately to its right. Both share the same `_fetch_etf_drawdown` cache (keyed per ticker; highs refreshed once per calendar day, bumped up if `last_price` exceeds the cached high). Custom table holds up to `MAX_CUSTOM_TICKERS` (=4) user-chosen tickers with per-row `×` delete buttons and an Add entry + button (disabled when full). On Add: ticker is validated via `validate_ticker()` on a worker thread, then drawdowns are fetched async and rendered. List persists to `custom_tickers.json` in the project dir.

### Toggle interaction matrix
| Toggle | Scatter | Treemap | Ticker bar | Tag bar |
|---|---|---|---|---|
| **Log X axis** | x-axis scale | — | — | — |
| **Group Tickers** | grouped dots | grouped tiles | grouped bars | always grouped |
| **Return %** | Y axis | — | X axis | — |
| **Sort A–Z** | — | — | sort order | sort order |

### Bottom panes — `ttk.PanedWindow` (horizontal, resizable)
Pane order and initial weights: **treemap (7) | scatter (9) | ticker bar (6) | tag bar (7)**

- **Treemap** — tiles sized by `abs(PnL)`, colored flat green/red by sign of `% move` (`PNL_POS_COLOR` / `PNL_NEG_COLOR`); labels show ticker + `±N.N%`, hidden if `min(dx,dy) ≤ fig_w * 0.06`; y-axis is inverted (squarify uses upper-left origin); redraws on resize with 150 ms debounce
- **Scatter** — X: SOD VALUE, Y: PnL or Return; UBS=blue, 401K=orange, multi-source=purple (`#9467bd`); hover shows source breakdown in grouped mode
- **Ticker bar** — scrollable horizontal bar chart; row height 0.28 in, min 3.0 in; bar resize debounced 50 ms; hover shows description + % move
- **Tag bar** — same layout as ticker bar; always grouped by `Tag`; ignores Group Tickers and Return % toggles; hover shows tickers, symbols, SOD VALUE, PnL for the tag

## Key Contracts
- `build_bar_df(df, sort_by_name, grouped, return_mode)` → always has `Label`, `Source`, `Value` columns; `draw_bar` is shared for both bar charts
- `build_tag_bar_df(df, sort_by_name)` → has `Label`, `Tag`, `Value`; no `return_mode`
- `build_grouped_scatter_df(df)` → one row per `Ticker Alias` with summed `PnL`, summed `SOD VALUE`, comma-joined `Sources`, and a `Return` column
- `draw_scatter(ax, df, log_x, grouped, return_mode)` → returns the DataFrame that was plotted (grouped or per-position); stored as `state.scatter_df` for hover + CSV export
- `draw_treemap(ax, df, grouped)` → returns `(rects, plot_data)`; `rects` are squarify dicts with `x, y, dx, dy` used for hover hit-testing
- `get_price_data(ticker)` → `(last_price, last_close, pct_move)` or `(None, None, None)`; transparently adjusts `last_close` for detected splits
- `load_and_compute(status_cb=None)` → concatenates UBS + 401K holdings, fetches prices in parallel, fills `Last Price`, `Last Close`, `% Move On Day`, `PnL`; `status_cb` receives stage labels for the status bar

## Non-obvious Behavior / Gotchas
- `% Move On Day` is a **decimal** (not ×100). `PnL = SOD VALUE * % Move On Day`.
- All tkinter calls from background threads must go through `root.after(0, ...)` — both `_run_worker` and `_auto_worker` rely on this.
- Bar resize: `bar_canvas_widget.config(width=w, height=h_px)` triggers matplotlib's `<Configure>` handler (recreates `_tkphoto`). Do **not** unbind it. Always also call `bar_canvas.draw()` explicitly — needed when size is unchanged (e.g., sort toggle).
- Bar/tag bar hover uses `round(event.ydata)` for hit detection — `bar.contains(event)` is unreliable on Windows with DPI scaling.
- Treemap hover iterates `state.treemap_rects` (squarify rect bounds); `state.treemap_df` holds the matching rows.
- Auto-update: `toggle_auto` cancels both `auto_after_id` (next run) and `countdown_id` (per-second label tick) — both must be tracked separately on `AppState`.
- Auto-detected stock splits silently rewrite `last_close` inside `get_price_data` — if a price looks "too good", check stdout for the `Note: detected N:1 split` line before assuming a bug.

## Git
- Always include `.claude/` directory in commits.
- Remote: https://github.com/marange63/PnL-Monitor.git
