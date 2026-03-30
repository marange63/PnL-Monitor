# PnL-Monitor

## Project Overview
Daily portfolio PnL monitor covering a UBS brokerage account and a UBS 401k account. Pulls live holdings from `claudedev_shared`, enriches with real-time Yahoo Finance prices, computes intraday P&L per position and in aggregate, and displays everything in a tkinter GUI with live charts.

## Environment
- **Conda env:** `PnL-Monitor` (`C:\Users\wamfo\anaconda3\envs\PnL-Monitor`) — always use this, not system Python
- **Python interpreter:** `C:\Users\wamfo\anaconda3\envs\PnL-Monitor\python.exe`
- **IDE:** PyCharm
- **GitHub:** https://github.com/marange63/PnL-Monitor (branch: `main`)
- **Deps:** `environment.yml` — `claudedev_shared`, `yfinance>=1.2.0`, `pandas>=2.3.0`, `matplotlib>=3.10.0`, `squarify`

## Data Sources
- `ubs_live_price_holdings()` / `ubs_401k_holdings()` — from `claudedev_shared`; both return a DataFrame with `DESCRIPTION`, `SYMBOL`, `SOD VALUE`, `Ticker Alias`, `Tag`, `Source`
- yfinance `fast_info`: use `last_price` and `regular_market_previous_close` (**not** `previous_close`, which includes after-hours)

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
| `data.py` | `get_price_data(ticker)`, `load_and_compute(status_cb)` |
| `charts.py` | `draw_scatter`, `draw_bar`, `draw_treemap`, `build_grouped_scatter_df`, `build_bar_df`, `build_tag_bar_df`, `dollar_fmt`, `pct_fmt` |
| `app.py` | `AppState` dataclass, `PnLApp` class |
| `main.py` | 3-line entry point |

## GUI Layout

### Top control strip
Run · Auto Update (60 s loop, countdown label) · Log X axis · Group Tickers · Return % · Sort A–Z · Export CSV · status label · PnL summary (UBS / 401K / Total)

### Toggle interaction matrix
| Toggle | Scatter | Treemap | Ticker bar | Tag bar |
|---|---|---|---|---|
| **Log X axis** | x-axis scale | — | — | — |
| **Group Tickers** | grouped dots | grouped tiles | grouped bars | always grouped |
| **Return %** | Y axis | — | X axis | — |
| **Sort A–Z** | — | — | sort order | sort order |

### Bottom panes — `ttk.PanedWindow` (horizontal, resizable)
Pane order and initial weights: **treemap (7) | scatter (9) | ticker bar (6) | tag bar (7)**

- **Treemap** — tiles sized by `abs(PnL)`, colored by `% move` (RdYlGn, symmetric); labels show ticker + `±N.N%`; redraws on resize with 150 ms debounce
- **Scatter** — X: SOD VALUE, Y: PnL or Return; UBS=blue, 401K=orange, multi-source=purple (`#9467bd`); hover shows source breakdown in grouped mode
- **Ticker bar** — scrollable horizontal bar chart; row height 0.28 in, min 3.0 in; hover shows description + % move
- **Tag bar** — same layout as ticker bar; always grouped by `Tag`; ignores Group Tickers and Return % toggles

## Key Contracts
- `build_bar_df(df, sort_by_name, grouped, return_mode)` → always has `Label`, `Source`, `Value` columns; `draw_bar` is shared for both bar charts
- `build_tag_bar_df(df, sort_by_name)` → has `Label`, `Tag`, `Value`; no `return_mode`
- `draw_treemap(ax, df, grouped)` → returns `(rects, plot_data)`; `rects` are squarify dicts with `x, y, dx, dy` used for hover hit-testing
- `get_price_data(ticker)` → `(last_price, last_close, pct_move)` or `(None, None, None)`

## Non-obvious Behavior / Gotchas
- `% Move On Day` is a **decimal** (not ×100). `PnL = SOD VALUE * % Move On Day`.
- All tkinter calls from background threads must go through `root.after(0, ...)`.
- Bar resize: `bar_canvas_widget.config(width=w, height=h_px)` triggers matplotlib's `<Configure>` handler (recreates `_tkphoto`). Do **not** unbind it. Always also call `bar_canvas.draw()` explicitly — needed when size is unchanged (e.g., sort toggle).
- Bar/tag bar hover uses `round(event.ydata)` for hit detection — `bar.contains(event)` is unreliable on Windows with DPI scaling.
- Treemap hover iterates `state.treemap_rects` (squarify rect bounds); `state.treemap_df` holds the matching rows.

## Git
- Always include `.claude/` directory in commits.
- Remote: https://github.com/marange63/PnL-Monitor.git
