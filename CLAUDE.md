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

## DataFrame Columns (computed in `data.py`)
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

## Module Structure

| File | Contents |
|---|---|
| `constants.py` | Named constants: colors, intervals, sizing |
| `data.py` | `get_price_data(ticker)`, `load_and_compute(status_cb)` |
| `charts.py` | `dollar_fmt`, `pct_fmt`, `draw_scatter()`, `build_grouped_scatter_df()`, `build_bar_df()`, `draw_bar()` |
| `app.py` | `AppState` dataclass, `PnLApp` class |
| `main.py` | 3-line entry point: `root = tk.Tk(); PnLApp(root); root.mainloop()` |

## GUI Layout

### Top control strip (spans full width)
- **Run** button — single manual run in a background thread
- **Auto Update** button — runs every 60 s; label changes to **Stop (Ns)** with live countdown while active
- **Log X axis** checkbox (default: **on**) — toggles scatter x-axis between linear and log scale
- **Group Tickers** checkbox (default: **on**) — collapses both charts to one entry per Ticker Alias (PnL/SOD VALUE summed); when off, shows one entry per position
- **Return %** checkbox (default: **off**) — switches both chart axes from PnL ($) to Return (PnL/SOD VALUE); bar annotations show `+1.23%` format
- **Sort A–Z** checkbox — bar chart sorted alphabetically (default: sorted by absolute value, largest at top)
- Status label — shows progress ("Loading holdings...", "Getting prices...", "Calculating PnL...", "Done.")
- PnL summary box (grooved border, centered) — **UBS PnL**, **401K PnL**, **Total PnL** (colored green/red)

### Bottom left — Scatter plot (column weight 3)
- X axis: SOD VALUE ($) [log or linear]; Y axis: PnL ($) or Return (%)
- **Ungrouped**: one dot per position; UBS = blue (`#1f77b4`), 401K = orange (`#ff7f0e`)
- **Grouped**: one dot per Ticker Alias (summed); single-source inherits source color; multi-source = purple (`#9467bd`)
- Each point labelled with `Ticker Alias`; dashed zero line
- Hover tooltip: Source / SOD VALUE / PnL or Return; grouped mode also shows per-source breakdown
- Resizes with window via matplotlib's built-in `<Configure>` handler

### Bottom right — Scrollable bar chart (column weight 2)
- **Grouped** (default): one bar per Ticker Alias, PnL or Return summed/weighted across accounts
- **Ungrouped**: one bar per position, labelled `"TICKER (Source)"`
- Green bars (`#2ca02c`) positive, red (`#d62728`) negative; thin black border
- Value labels right of positive bars, left of negative bars
- Row height: 0.28 inches; figure height auto-sizes; minimum 3.0 inches
- Vertically scrollable (mouse wheel); width tracks panel width on resize
- Hover tooltip: security description + ticker + % move on day (ungrouped also shows source)

## `AppState` dataclass (`app.py`)
```python
@dataclass
class AppState:
    plot_df: Optional[pd.DataFrame] = None      # full per-position DataFrame
    scatter_df: Optional[pd.DataFrame] = None   # currently plotted scatter data (may be grouped)
    current_bar_df: Optional[pd.DataFrame] = None
    auto_running: bool = False
    auto_after_id: Optional[str] = None
    countdown_id: Optional[str] = None
    bar_resize_id: Optional[str] = None
```

## `PnLApp` key methods (`app.py`)
- `_build_controls()` / `_build_scatter()` / `_build_bar()` / `_build_tooltip()` — GUI construction
- `_run_worker()` — background thread: calls `load_and_compute`, schedules `_update_ui` via `root.after(0, ...)`
- `_redraw_scatter()` — redraws scatter from `state.plot_df` respecting current toggle states
- `redraw_bar()` — redraws bar chart; always ends with `bar_canvas.draw()` so sort changes render without a size change
- `_redraw_all()` — calls both (used by Group Tickers and Return % toggles)
- `toggle_auto()`, `_start_auto_run()`, `_auto_worker()`, `_start_countdown()` — auto-update loop
- `_show_tooltip(text, widget, event)` — shared helper for both hover handlers
- `_on_hover(event)` — scatter hover; uses `coll.contains(event)` for hit detection
- `_on_bar_hover(event)` — bar hover; uses `round(event.ydata)` (NOT `bar.contains`) to avoid DPI offset bugs

## `charts.py` key functions
- `draw_scatter(ax, df, log_x, grouped, return_mode)` → returns plotted DataFrame
- `build_grouped_scatter_df(df)` → groups by Ticker Alias, adds `Return = PnL/SOD VALUE` and `Sources` columns
- `build_bar_df(df, sort_by_name, grouped, return_mode)` → always includes `Label`, `Source`, `Value` columns
- `draw_bar(ax_bar, bar_df, return_mode)` — uses `bar_df['Label']` for y-axis and `bar_df['Value']` for widths
- `dollar_fmt`, `pct_fmt` — shared axis formatters

## `data.py` key functions
- `get_price_data(ticker)` → `(last_price, last_close, pct_move)` or `(None, None, None)`
- `load_and_compute(status_cb=None)` → full pipeline: load holdings, concurrent price fetch, compute PnL; calls `status_cb(msg)` for progress updates

## Important Notes
- Use `regular_market_previous_close` (not `previous_close`) for the prior close.
- `% Move On Day` is a decimal (not ×100). `PnL = SOD VALUE * % Move On Day`.
- All tkinter widget updates from background threads go through `root.after(0, ...)`.
- Bar chart resize: `bar_canvas_widget.config(width=w, height=h_px)` triggers matplotlib's `<Configure>` handler which recreates `_tkphoto`. Do NOT unbind that handler. Always also call `bar_canvas.draw()` explicitly so content redraws when size is unchanged (e.g., sort toggle).
- Bar hover uses `round(event.ydata)` to find bar index — `bar.contains(event)` is unreliable on Windows with DPI scaling.
- `bar_df['Value']` holds the display value (PnL $ or Return decimal); `bar_df['Label']` holds the y-axis label.

## Git
- Always include `.claude/` directory in commits.
- Remote: https://github.com/marange63/PnL-Monitor.git
