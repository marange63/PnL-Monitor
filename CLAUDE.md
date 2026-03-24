# PnL-Monitor

## Project Overview
Daily portfolio PnL monitor covering a UBS brokerage account and a UBS 401k account. Pulls live holdings from an internal shared library, enriches them with real-time price data from Yahoo Finance, computes intraday P&L per position and in aggregate, and displays everything in a tkinter GUI with live charts.

## Repository
- GitHub: https://github.com/marange63/PnL-Monitor
- Branch: `main`

## Environment
- **Conda env:** `PnL-Monitor` (`C:\Users\wamfo\anaconda3\envs\PnL-Monitor`)
- **Python interpreter:** `C:\Users\wamfo\anaconda3\envs\PnL-Monitor\python.exe`
- **IDE:** PyCharm

Always run Python via the PnL-Monitor conda environment, not the system Python.

## Key Dependencies
- `claudedev_shared` — internal shared library providing `ubs_live_price_holdings()` and `ubs_401k_holdings()`
- `yfinance>=1.2.0` — Yahoo Finance price data
- `pandas>=2.3.0`
- `matplotlib>=3.10.0` — charts embedded in tkinter via `FigureCanvasTkAgg`
- `tkinter` (stdlib) — GUI
- `concurrent.futures` (stdlib) — concurrent ticker fetching
- `threading` (stdlib) — background data fetch so GUI stays responsive

## Dependency File
- `environment.yml` — conda environment definition (Python 3.13, yfinance, pandas, matplotlib)

## Data Sources
### `ubs_live_price_holdings()` (from `claudedev_shared`)
Returns a DataFrame with columns:
- `DESCRIPTION` — full name of the security
- `SYMBOL` — brokerage symbol
- `SOD VALUE` — start-of-day position value in USD
- `Ticker Alias` — Yahoo Finance-compatible ticker symbol

### `ubs_401k_holdings()` (from `claudedev_shared`)
Returns a DataFrame with the same schema as `ubs_live_price_holdings()`.
Source file: `C:\Users\wamfo\ClaudeDev\data\UBS 401K.csv` with ticker aliases from `Ticker-Aliases-401K.csv`.

### yfinance (`fast_info`)
Used fields:
- `last_price` — current/latest price
- `regular_market_previous_close` — official prior regular session close (**not** `previous_close`, which includes after-hours)

## DataFrame Columns (computed in `main.py`)
| Column | Description |
|---|---|
| `DESCRIPTION` | Security full name |
| `SYMBOL` | Brokerage symbol |
| `SOD VALUE` | Start-of-day USD value |
| `Ticker Alias` | Yahoo Finance ticker |
| `Source` | Account source: `"UBS"` or `"401K"` (set by `claudedev_shared`) |
| `Last Price` | Current price from yfinance |
| `Last Close` | Prior regular session close (`regular_market_previous_close`) |
| `% Move On Day` | `(Last Price - Last Close) / Last Close` (decimal, e.g. 0.0179 = 1.79%) |
| `PnL` | `SOD VALUE * % Move On Day` — intraday USD P&L per position |

## GUI Layout (`main.py`)

### Top control strip (spans full width)
- **Run** button — single manual run in a background thread
- **Auto Update** button — runs every 60 s; label changes to **Stop (Ns)** with live countdown while active
- **Log X axis** checkbox — toggles scatter plot x-axis between linear and log scale
- Status label — shows progress ("Loading holdings...", "Getting prices...", "Calculating PnL...", "Done.")
- PnL summary box (grooved border, centered) — three labeled fields: **UBS PnL**, **401K PnL**, **Total PnL**

### Bottom left — Scatter plot (weight 3)
- X axis: SOD VALUE ($), Y axis: PnL ($)
- Points coloured by Source: UBS = blue (`#1f77b4`), 401K = orange (`#ff7f0e`)
- Each point labelled with its `Ticker Alias`
- Dashed zero line
- Dollar-formatted axes; x-axis capped at 6 ticks via `MaxNLocator`
- Hover tooltip (yellow Toplevel popup) shows Source, SOD VALUE, PnL
- Resizes with window via matplotlib's built-in `<Configure>` handler

### Bottom right — Scrollable bar chart (weight 2)
- Horizontally grouped by `Ticker Alias` (PnL summed across accounts)
- Sorted descending by absolute PnL (largest at top)
- Green bars (`#2ca02c`) for positive PnL, red (`#d62728`) for negative
- Thin black border (`edgecolor='black', linewidth=0.5`) on each bar
- PnL value labels: to the right for positive, to the left for negative
- Row height: 0.28 inches per ticker; figure height auto-sizes after each run
- Vertically scrollable (mouse wheel supported); width tracks panel width on resize
- Resize: `bar_scroll_canvas <Configure>` → debounced 50 ms → `bar_canvas_widget.config(width, height)` triggers matplotlib's internal resize handler

## Code Structure

### Module-level
- `get_price_data(ticker)` — fetches `(last_price, last_close, pct_move)` from yfinance; returns `(None, None, None)` on failure

### `run_pnl(...)` — main data function (runs in background thread)
Parameters: `status_var, result_vars, run_btn, ax, canvas, ax_bar, bar_canvas, bar_scroll_canvas, plot_df`
1. Loads holdings, fetches prices concurrently via `ThreadPoolExecutor`
2. Computes PnL, updates summary fields
3. Stores full DataFrame in `plot_df[0]` (for hover tooltip lookup)
4. Redraws scatter plot and bar chart
5. Resizes bar chart widget to fit ticker count

### `__main__` state containers (mutable lists used as closures)
- `plot_df = [None]` — latest DataFrame, used by hover tooltip
- `auto_running = [False]` — auto-update loop flag
- `auto_after_id = [None]` — handle for pending `root.after` run
- `countdown_id = [None]` — handle for countdown ticker
- `_bar_resize_id = [None]` — debounce handle for bar chart resize

## Important Notes
- Use `regular_market_previous_close` (not `previous_close`) for the prior close.
- `% Move On Day` is a decimal (not ×100). `PnL = SOD VALUE * % Move On Day`.
- All tkinter widget updates from background threads go through `root.after(0, ...)`.
- Bar chart resize relies on matplotlib's internal `<Configure>` handler — do NOT unbind it. Trigger resize by calling `bar_canvas_widget.config(width=w, height=h_px)`.
- `bar_window_id` is a module-level name captured by the `run_pnl` closure; it must remain in scope.

## Git
- Always include `.claude/` directory in commits.
- Remote: https://github.com/marange63/PnL-Monitor.git
