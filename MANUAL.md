# PnL Monitor — Developer's User Manual

## Table of Contents

1. [Introduction](#1-introduction)
2. [Prerequisites](#2-prerequisites)
3. [Installation & Setup](#3-installation--setup)
4. [Running the Application](#4-running-the-application)
5. [User Interface Guide](#5-user-interface-guide)
   - [Control Strip](#51-control-strip)
   - [PnL Summary](#52-pnl-summary)
   - [Treemap Pane](#53-treemap-pane)
   - [Scatter Plot Pane](#54-scatter-plot-pane)
   - [Ticker Bar Chart Pane](#55-ticker-bar-chart-pane)
   - [Tag Bar Chart Pane](#56-tag-bar-chart-pane)
6. [Toggle Controls Reference](#6-toggle-controls-reference)
7. [Tooltips & Hover Behavior](#7-tooltips--hover-behavior)
8. [Architecture & Module Reference](#8-architecture--module-reference)
   - [main.py](#81-mainpy)
   - [app.py](#82-apppy)
   - [data.py](#83-datapy)
   - [charts.py](#84-chartspy)
   - [constants.py](#85-constantspy)
9. [Data Pipeline](#9-data-pipeline)
   - [Holdings Ingestion](#91-holdings-ingestion)
   - [Price Enrichment](#92-price-enrichment)
   - [PnL Computation](#93-pnl-computation)
   - [DataFrame Schema](#94-dataframe-schema)
10. [Key Functions & API Reference](#10-key-functions--api-reference)
11. [Threading Model](#11-threading-model)
12. [Resize & Scroll Behavior](#12-resize--scroll-behavior)
13. [Configuration & Constants](#13-configuration--constants)
14. [Dependencies](#14-dependencies)
15. [Known Behaviors & Gotchas](#15-known-behaviors--gotchas)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Introduction

PnL Monitor is a daily portfolio profit-and-loss monitoring tool built with Python and tkinter. It tracks holdings across a UBS brokerage account and a UBS 401(k) account, enriches them with real-time prices from Yahoo Finance, computes intraday P&L per position and in aggregate, and displays everything in an interactive GUI with four synchronized chart panes.

The application is designed for intraday use during market hours. It supports manual one-shot refreshes and a 60-second auto-update loop that continuously pulls fresh prices.

---

## 2. Prerequisites

- **Operating System:** Windows 10/11 (the GUI uses Windows-specific DPI handling and Segoe UI fonts)
- **Anaconda/Miniconda:** Required for managing the conda environment
- **Python:** 3.13 (managed by conda)
- **GitHub access:** Repository at https://github.com/marange63/PnL-Monitor
- **`claudedev_shared` package:** A private package that provides the `ubs_live_price_holdings()` and `ubs_401k_holdings()` functions. This must be installed and properly configured before the application will run.
- **Internet connection:** Required for Yahoo Finance price lookups

---

## 3. Installation & Setup

### Clone the repository

```bash
git clone https://github.com/marange63/PnL-Monitor.git
cd PnL-Monitor
```

### Create the conda environment

```bash
conda env create -f environment.yml
conda activate PnL-Monitor
```

This installs all dependencies listed in `environment.yml`:

| Package | Version | Purpose |
|---|---|---|
| `python` | 3.13 | Runtime |
| `yfinance` | >= 1.2.0 | Real-time stock prices from Yahoo Finance |
| `pandas` | >= 2.3.0 | DataFrame operations and data manipulation |
| `matplotlib` | >= 3.10.0 | Chart rendering (scatter, bar, treemap) |
| `squarify` | >= 0.4.3 | Treemap layout algorithm |
| `sv-ttk` | >= 2.6.0 | Sun Valley light theme for tkinter |
| `claudedev_shared` | latest | Holdings data source (private package) |

### Verify installation

```bash
conda activate PnL-Monitor
python -c "from claudedev_shared import ubs_live_price_holdings; print('OK')"
```

If this prints `OK`, the environment is ready.

---

## 4. Running the Application

```bash
conda activate PnL-Monitor
python main.py
```

Or from PyCharm: set the project interpreter to `C:\Users\wamfo\anaconda3\envs\PnL-Monitor\python.exe` and run `main.py`.

The application window opens in the Sun Valley light theme. No data is loaded on startup — click **Run** or **Auto Update** to begin.

---

## 5. User Interface Guide

The window is divided into two main areas: a **top control strip** (with buttons, toggles, status, and PnL summary) and a **bottom chart area** with four resizable panes arranged horizontally.

### 5.1 Control Strip

Located at the top of the window. Contains, from left to right:

| Control | Type | Description |
|---|---|---|
| **Run** | Button | Triggers a single data fetch and refresh. Disabled while a fetch is in progress. |
| **Auto Update** | Button | Toggles a 60-second auto-refresh loop. While active, the button text shows a countdown (e.g., `Stop (45s)`). Click again to stop. |
| **Log X axis** | Checkbox | Switches the scatter plot X-axis between linear and logarithmic scale. Default: checked (log). |
| **Group Tickers** | Checkbox | When checked, positions with the same ticker across UBS and 401K are merged into a single data point. Default: checked. |
| **Return %** | Checkbox | Switches the scatter Y-axis and ticker bar X-axis between dollar PnL and percentage return. Default: unchecked (dollar PnL). |
| **Sort A–Z** | Checkbox | Sorts the ticker bar and tag bar alphabetically instead of by absolute value. Default: unchecked (by magnitude). |
| **Export CSV** | Button | Opens a Save dialog to export the current scatter plot data to a CSV file. |

Below the buttons is a **status label** (gray text) showing the current operation state (e.g., "Loading holdings...", "Getting prices...", "Done. Last update: 14:32:05").

### 5.2 PnL Summary

A labeled frame below the status line displaying three values:

| Field | Description |
|---|---|
| **UBS PnL** | Sum of PnL for all positions where `Source = "UBS"` |
| **401K PnL** | Sum of PnL for all positions where `Source = "401K"` |
| **Total PnL** | Sum of PnL across all positions |

Each value is color-coded: **green** (`#2ca02c`) for positive, **red** (`#d62728`) for negative.

### 5.3 Treemap Pane

**Position:** Leftmost pane (initial weight: 7)

Displays a treemap where:
- **Tile size** is proportional to `abs(PnL)` — larger absolute P&L = larger tile
- **Tile color** is flat green for positive moves and flat red for negative moves
- **Tile labels** show the ticker symbol and percentage move (e.g., `AAPL\n+1.2%`). Labels are hidden on tiles that are too small (< 6% of figure width).

The treemap redraws on pane resize with a **150 ms debounce** to prevent excessive redraws during drag operations.

Respects the **Group Tickers** toggle: when grouped, positions with the same ticker are aggregated.

### 5.4 Scatter Plot Pane

**Position:** Second pane (initial weight: 9)

A scatter plot of all positions:
- **X-axis:** SOD VALUE (start-of-day dollar value of the position)
- **Y-axis:** PnL in dollars, or Return % when the Return % toggle is active
- **Dot colors:** Blue (`#1f77b4`) for UBS, Orange (`#ff7f0e`) for 401K, Purple (`#9467bd`) for tickers that appear in both sources (only visible when Group Tickers is checked)
- Each dot is annotated with its ticker symbol

The X-axis can be toggled between linear and logarithmic scale using the **Log X axis** checkbox.

### 5.5 Ticker Bar Chart Pane

**Position:** Third pane (initial weight: 6)

A horizontal bar chart with one bar per ticker (or per position when ungrouped):
- **Bar length** represents PnL in dollars or percentage return
- **Bar color:** Green for positive, red for negative
- **Bar labels** show the dollar or percentage value next to each bar
- **Row height:** 0.28 inches per bar, minimum chart height of 3.0 inches
- Scrollable vertically via mouse wheel when content exceeds the pane height

Respects: **Group Tickers**, **Return %**, **Sort A–Z**.

### 5.6 Tag Bar Chart Pane

**Position:** Rightmost pane (initial weight: 7)

Same visual layout as the ticker bar chart, but bars represent sector/category **tags** instead of individual tickers:
- Always grouped by the `Tag` column — the Group Tickers toggle has no effect
- Always shows dollar PnL — the Return % toggle has no effect
- Respects the **Sort A–Z** toggle

Scrollable vertically via mouse wheel.

---

## 6. Toggle Controls Reference

This matrix shows which toggles affect which chart panes:

| Toggle | Scatter | Treemap | Ticker Bar | Tag Bar |
|---|---|---|---|---|
| **Log X axis** | X-axis scale | — | — | — |
| **Group Tickers** | Grouped dots | Grouped tiles | Grouped bars | Always grouped (no effect) |
| **Return %** | Y-axis unit | — | X-axis unit | — (always dollar PnL) |
| **Sort A–Z** | — | — | Sort order | Sort order |

---

## 7. Tooltips & Hover Behavior

All four chart panes support hover tooltips. A tooltip appears as a small yellow popup near the cursor when hovering over a data element.

### Scatter Plot Tooltip

**Ungrouped mode:**
```
Ticker:         AAPL
Symbol:        AAPL
Source:        UBS
SOD VALUE:  $15,234.00
PnL:  $182.00
```

**Grouped mode** (additional lines showing per-source breakdown):
```
Ticker:         IGV
Symbols:       IGV
Sources:       401K, UBS
SOD VALUE:  $28,500.00
Total PnL:  $340.00
  401K PnL:  $120.00
  UBS PnL:  $220.00
```

### Treemap Tooltip
```
Ticker:        AAPL
SOD VALUE: $15,234
PnL:           $182
Move:         +1.20%
```

### Ticker Bar Tooltip
Shows the security's full description name and percentage move:
```
Apple Inc.
AAPL:  +1.20%
```

### Tag Bar Tooltip
Shows the tag's aggregated data and constituent tickers/symbols:
```
Tag: Technology
SOD VALUE:  $85,400
PnL: $1,023
Tickers: AAPL, MSFT, XLK
Symbols: AAPL, MSFT, XLK
```

**Technical note:** Bar chart hover detection uses `round(event.ydata)` for hit-testing rather than matplotlib's `bar.contains(event)`, which is unreliable on Windows with DPI scaling.

---

## 8. Architecture & Module Reference

```
PnL-Monitor/
├── main.py          # Entry point (3 lines)
├── app.py           # GUI application class and state management
├── data.py          # Data loading, price fetching, PnL computation
├── charts.py        # All chart drawing and DataFrame building functions
├── constants.py     # Named constants (colors, intervals, sizing)
├── environment.yml  # Conda environment specification
├── CLAUDE.md        # Developer reference for AI-assisted development
└── MANUAL.md        # This file
```

### 8.1 main.py

The entry point. Creates a tkinter root window, applies the Sun Valley light theme, instantiates `PnLApp`, and starts the main loop.

```python
root = tk.Tk()
sv_ttk.set_theme("light")
PnLApp(root)
root.mainloop()
```

### 8.2 app.py

Contains two classes:

**`AppState`** — A dataclass holding all mutable application state:

| Field | Type | Description |
|---|---|---|
| `plot_df` | `DataFrame` or `None` | The full per-position DataFrame after price enrichment |
| `scatter_df` | `DataFrame` or `None` | The DataFrame currently displayed in the scatter plot (may be grouped) |
| `current_bar_df` | `DataFrame` or `None` | The DataFrame currently displayed in the ticker bar chart |
| `current_tag_bar_df` | `DataFrame` or `None` | The DataFrame currently displayed in the tag bar chart |
| `treemap_rects` | `list` or `None` | List of squarify rect dicts (`x`, `y`, `dx`, `dy`) for hover hit-testing |
| `treemap_df` | `DataFrame` or `None` | DataFrame matching the treemap tiles (for tooltip data) |
| `auto_running` | `bool` | Whether auto-update loop is active |
| `auto_after_id` | `str` or `None` | tkinter `after()` ID for the next auto-update cycle |
| `countdown_id` | `str` or `None` | tkinter `after()` ID for the countdown timer |
| `bar_resize_id` | `str` or `None` | Debounce ID for ticker bar resize |
| `tag_bar_resize_id` | `str` or `None` | Debounce ID for tag bar resize |
| `treemap_resize_id` | `str` or `None` | Debounce ID for treemap resize |

**`PnLApp`** — The main application class. Constructor builds the entire GUI via private `_build_*` methods. Key method groups:

| Method Group | Purpose |
|---|---|
| `_build_controls`, `_build_scatter`, `_build_bar`, `_build_tag_bar`, `_build_treemap`, `_build_tooltip` | GUI construction |
| `_run_worker`, `_auto_worker` | Background data fetch and UI update |
| `toggle_auto`, `_start_auto_run`, `_start_countdown` | Auto-update loop management |
| `_redraw_scatter`, `redraw_treemap`, `redraw_bar`, `redraw_tag_bar` | Chart redraw after data or toggle change |
| `_on_hover`, `_on_bar_hover`, `_on_treemap_hover`, `_on_tag_bar_hover` | Tooltip event handlers |
| `_on_bar_area_resize`, `_on_tag_area_resize`, `_on_treemap_resize` | Resize event handlers with debouncing |
| `_toggle_log_x`, `_toggle_group`, `_redraw_all`, `_redraw_bars` | Toggle callbacks |
| `_export_scatter_csv` | CSV export of scatter data |

### 8.3 data.py

Two public functions:

**`get_price_data(ticker)`** — Fetches the current price, previous close, and percentage move for a single ticker via `yfinance`. Retries once with a 0.5-second delay on failure. Returns `(last_price, last_close, pct_move)` or `(None, None, None)`.

**`load_and_compute(status_cb=None)`** — The full data pipeline:
1. Loads holdings from both accounts via `claudedev_shared`
2. Concatenates into a single DataFrame
3. Fetches prices for all tickers concurrently (5 threads max)
4. Computes `PnL = SOD VALUE * % Move On Day`
5. Returns the enriched DataFrame

The optional `status_cb` callback receives progress strings for UI display.

### 8.4 charts.py

**Drawing functions:**

| Function | Signature | Returns |
|---|---|---|
| `draw_treemap` | `(ax, df, grouped=False)` | `(rects, plot_data)` — rect dicts + DataFrame for hover |
| `draw_scatter` | `(ax, df, log_x, grouped, return_mode)` | `plot_data` — the DataFrame that was plotted |
| `draw_bar` | `(ax_bar, bar_df, return_mode=False)` | None — shared by both ticker and tag bar charts |

**DataFrame building functions:**

| Function | Signature | Returns |
|---|---|---|
| `build_grouped_scatter_df` | `(df)` | Grouped DataFrame with `Ticker Alias`, `PnL`, `SOD VALUE`, `Sources`, `Return` |
| `build_bar_df` | `(df, sort_by_name, grouped, return_mode)` | DataFrame with `Label`, `Source`, `Value` columns |
| `build_tag_bar_df` | `(df, sort_by_name)` | DataFrame with `Label`, `Tag`, `Value` columns |

**Formatters:**

| Name | Format | Example |
|---|---|---|
| `dollar_fmt` | `$X,XXX` | `$1,234` |
| `pct_fmt` | `+X.XX%` | `+1.79%` |

### 8.5 constants.py

| Constant | Value | Purpose |
|---|---|---|
| `AUTO_UPDATE_INTERVAL_MS` | `60000` | Milliseconds between auto-update cycles |
| `AUTO_UPDATE_COUNTDOWN_SECS` | `59` | Countdown starting value displayed on button |
| `BAR_ROW_HEIGHT_INCHES` | `0.28` | Height per bar in the bar charts |
| `BAR_MIN_HEIGHT_INCHES` | `3.0` | Minimum height of bar chart canvases |
| `BAR_RESIZE_DEBOUNCE_MS` | `50` | Debounce delay for bar chart resize events |
| `SOURCE_COLORS` | `{"UBS": "#1f77b4", "401K": "#ff7f0e"}` | Blue for UBS, orange for 401K |
| `MULTI_SOURCE_COLOR` | `"#9467bd"` | Purple for tickers in both sources |
| `PNL_POS_COLOR` | `"#2ca02c"` | Green for positive PnL |
| `PNL_NEG_COLOR` | `"#d62728"` | Red for negative PnL |

---

## 9. Data Pipeline

### 9.1 Holdings Ingestion

The `claudedev_shared` package provides two functions:

- `ubs_live_price_holdings()` — Returns a DataFrame of UBS brokerage holdings
- `ubs_401k_holdings()` — Returns a DataFrame of UBS 401(k) holdings

Both return DataFrames with columns: `DESCRIPTION`, `SYMBOL`, `SOD VALUE`, `Ticker Alias`, `Tag`, `Source`.

The two DataFrames are concatenated into a single DataFrame.

### 9.2 Price Enrichment

For each unique `Ticker Alias` in the combined DataFrame, `get_price_data()` calls the Yahoo Finance API via `yfinance`:

```python
data = yf.Ticker(ticker).fast_info
last_price = data.last_price
last_close = data.regular_market_previous_close
```

**Important:** The code uses `regular_market_previous_close` (not `previous_close`), because `previous_close` includes after-hours trading and would produce incorrect intraday P&L calculations.

Price fetches run concurrently across 5 threads. Each fetch retries once on failure with a 0.5-second delay, to handle intermittent Yahoo Finance rate-limiting.

### 9.3 PnL Computation

```
% Move On Day = (Last Price - Last Close) / Last Close
PnL = SOD VALUE * % Move On Day
```

`% Move On Day` is stored as a **decimal** (e.g., `0.0179` for a 1.79% move), not as a percentage.

### 9.4 DataFrame Schema

After `load_and_compute()` returns, the DataFrame contains:

| Column | Type | Source | Description |
|---|---|---|---|
| `DESCRIPTION` | str | `claudedev_shared` | Security full name (e.g., "Apple Inc.") |
| `SYMBOL` | str | `claudedev_shared` | Brokerage symbol |
| `SOD VALUE` | float | `claudedev_shared` | Start-of-day USD market value |
| `Ticker Alias` | str | `claudedev_shared` | Yahoo Finance ticker symbol |
| `Tag` | str | `claudedev_shared` | Sector/category classification |
| `Source` | str | `claudedev_shared` | `"UBS"` or `"401K"` |
| `Last Price` | float | yfinance | Current market price |
| `Last Close` | float | yfinance | Previous regular-session close |
| `% Move On Day` | float | Computed | Decimal price change ratio |
| `PnL` | float | Computed | Dollar profit/loss for this position today |

---

## 10. Key Functions & API Reference

### data.py

```python
get_price_data(ticker: str) -> tuple[float, float, float] | tuple[None, None, None]
```
Fetches `(last_price, last_close, pct_move)` for a single ticker. Retries once on failure. Returns `(None, None, None)` if both attempts fail.

```python
load_and_compute(status_cb: Callable[[str], None] | None = None) -> pd.DataFrame
```
Full pipeline: load holdings, fetch prices, compute PnL. The `status_cb` receives progress strings like `"Loading holdings..."`, `"Getting prices..."`, `"Calculating PnL..."`.

### charts.py

```python
draw_treemap(ax, df, grouped=False) -> tuple[list[dict], pd.DataFrame]
```
Draws the treemap on the given axes. Returns `(rects, plot_data)` where `rects` is a list of squarify dicts with keys `x`, `y`, `dx`, `dy` used for hover hit-testing, and `plot_data` is the corresponding DataFrame.

```python
draw_scatter(ax, df, log_x=False, grouped=False, return_mode=False) -> pd.DataFrame
```
Draws the scatter plot. Returns the plotted DataFrame (may be grouped).

```python
build_bar_df(df, sort_by_name=False, grouped=True, return_mode=False) -> pd.DataFrame
```
Builds the ticker bar chart DataFrame. Output always has `Label`, `Source`, `Value` columns.

```python
build_tag_bar_df(df, sort_by_name=False) -> pd.DataFrame
```
Builds the tag bar chart DataFrame. Output has `Label`, `Tag`, `Value` columns. Always groups by `Tag`; has no `return_mode` parameter.

```python
draw_bar(ax_bar, bar_df, return_mode=False) -> None
```
Shared drawing function used by both the ticker bar and tag bar charts. Draws horizontal bars with value labels and auto-expands axis limits by 30% to prevent label clipping.

```python
build_grouped_scatter_df(df) -> pd.DataFrame
```
Aggregates per-position rows into one row per `Ticker Alias`, summing `PnL` and `SOD VALUE`, and computing `Return = PnL / SOD VALUE`. The `Sources` column contains a comma-separated sorted list of unique sources.

---

## 11. Threading Model

The application uses a **single-threaded GUI with background workers** pattern:

- **Main thread:** Runs the tkinter event loop. All GUI updates must happen on this thread.
- **Worker threads:** `_run_worker()` and `_auto_worker()` run in daemon threads via `threading.Thread(daemon=True)`. They perform network I/O (Yahoo Finance) and data computation off the main thread.
- **Thread safety:** All GUI updates from worker threads are dispatched to the main thread via `root.after(0, callback)`. This is critical — calling tkinter methods directly from a background thread causes crashes.
- **Concurrency within workers:** `get_price_data()` is called via `ThreadPoolExecutor(max_workers=5)`, meaning up to 5 Yahoo Finance requests run in parallel within a single worker thread.

### Auto-update cycle

1. User clicks Auto Update → `toggle_auto()` sets `auto_running = True` and calls `_start_auto_run()`
2. `_start_auto_run()` spawns a daemon thread running `_auto_worker()`
3. `_auto_worker()` calls `_run_worker()` (blocking), then schedules the next cycle via `root.after(60000, _start_auto_run)` and starts the countdown display
4. User clicks Stop → `toggle_auto()` sets `auto_running = False` and cancels pending `after()` callbacks

---

## 12. Resize & Scroll Behavior

### Pane resizing

The four chart panes are children of a `ttk.PanedWindow` with horizontal orientation. Users can drag the dividers between panes to resize them. Initial size distribution is controlled by weights: treemap (7), scatter (9), ticker bar (6), tag bar (7).

### Bar chart scrolling

Both bar charts (ticker and tag) use a scrollable canvas architecture:

```
bar_outer (Frame)
├── bar_scroll_canvas (tk.Canvas) ← scrollable viewport
│   └── bar_canvas_widget (FigureCanvasTkAgg) ← matplotlib figure, may be taller than viewport
└── bar_scrollbar (ttk.Scrollbar)
```

The matplotlib figure height is calculated dynamically: `max(3.0 inches, num_bars * 0.28 inches)`. When there are many bars, the figure is taller than the visible area, and the user scrolls with the mouse wheel.

### Resize debouncing

- **Bar charts:** 50 ms debounce (`BAR_RESIZE_DEBOUNCE_MS`)
- **Treemap:** 150 ms debounce (hardcoded in `_on_treemap_resize`)

**Important:** The bar chart's `<Configure>` handler (from matplotlib's `FigureCanvasTkAgg`) must not be unbound. Setting `bar_canvas_widget.config(width=w, height=h_px)` triggers this handler, which recreates the internal `_tkphoto`. After changing content without changing size (e.g., toggling sort), you must explicitly call `bar_canvas.draw()`.

---

## 13. Configuration & Constants

All tunable values are in `constants.py`. To change the auto-update interval, bar sizing, or color scheme, edit this file.

### Color scheme

| Element | Color | Hex |
|---|---|---|
| UBS dots | Blue | `#1f77b4` |
| 401K dots | Orange | `#ff7f0e` |
| Multi-source dots | Purple | `#9467bd` |
| Positive PnL | Green | `#2ca02c` |
| Negative PnL | Red | `#d62728` |
| Chart background | White | via `set_facecolor('white')` |
| Grid lines | Light gray | `#e8e8e8` |
| Axis spines | Gray | `#cccccc` |

### Timing

| Parameter | Value | Description |
|---|---|---|
| Auto-update interval | 60 seconds | Time between refresh cycles |
| Bar resize debounce | 50 ms | Prevents rapid bar chart redraws during resize |
| Treemap resize debounce | 150 ms | Prevents rapid treemap redraws during resize |
| Price retry delay | 0.5 seconds | Wait before retrying a failed Yahoo Finance call |

---

## 14. Dependencies

### Runtime dependencies (in `environment.yml`)

| Package | Purpose |
|---|---|
| **yfinance** | Fetches real-time stock/ETF prices from Yahoo Finance. Uses the `fast_info` property for lightweight lookups. |
| **pandas** | Core data structure. All holdings and computed data flow through DataFrames. |
| **matplotlib** | Renders all four chart types. Embedded in tkinter via `FigureCanvasTkAgg`. |
| **squarify** | Computes treemap tile layouts. Takes a list of values and a bounding box, returns a list of rectangles. |
| **sv-ttk** | Sun Valley theme for tkinter's ttk widgets. Applied at startup with `sv_ttk.set_theme("light")`. |
| **claudedev_shared** | Private package providing `ubs_live_price_holdings()` and `ubs_401k_holdings()` functions that return holdings DataFrames. |

### Standard library modules used

`tkinter`, `threading`, `concurrent.futures`, `datetime`, `traceback`, `dataclasses`, `time`

---

## 15. Known Behaviors & Gotchas

1. **`% Move On Day` is a decimal, not a percentage.** A 1.79% move is stored as `0.0179`. PnL is computed as `SOD VALUE * 0.0179`, not `SOD VALUE * 1.79`. All display formatting multiplies by 100.

2. **`regular_market_previous_close` vs `previous_close`.** The code deliberately uses `regular_market_previous_close` from yfinance. The `previous_close` field includes after-hours price changes and would produce incorrect intraday P&L relative to the prior regular session close.

3. **Yahoo Finance intermittent failures.** Yahoo Finance's API occasionally returns empty responses under load. The application mitigates this by:
   - Limiting concurrent requests to 5 (via `ThreadPoolExecutor(max_workers=5)`)
   - Retrying once with a 0.5-second delay on failure
   - Gracefully handling failures with `(None, None, None)` return values

   Positions that fail both attempts will show `NaN` for price/PnL columns and will be excluded from charts.

4. **Thread safety.** All tkinter calls from background threads must go through `root.after(0, callback)`. Calling tkinter directly from a worker thread will cause crashes or visual corruption.

5. **Bar hover uses `round(event.ydata)`.** Matplotlib's `bar.contains(event)` is unreliable on Windows with DPI scaling. The code uses `round(event.ydata)` and a ±0.4 threshold for bar hit detection instead.

6. **Bar `<Configure>` handler must not be unbound.** Matplotlib's `FigureCanvasTkAgg` binds a `<Configure>` handler that recreates the internal `_tkphoto` bitmap. Removing this binding breaks rendering. When updating bar chart content without changing size, always call `bar_canvas.draw()` explicitly.

7. **Treemap label visibility.** Tile labels are only rendered when `min(rect['dx'], rect['dy']) > fig_w * 0.06`. Very small tiles will appear colored but unlabeled — hover over them to see their data.

8. **Export CSV exports scatter data.** The Export CSV button exports whatever the scatter plot is currently showing. If grouped, the CSV contains grouped data; if ungrouped, it contains per-position data.

---

## 16. Troubleshooting

### "Warning: failed to get price for TICKER: ..."

Yahoo Finance returned an error for that ticker. If this affects many tickers, it is likely rate-limiting. The retry mechanism handles most cases. If persistent:
- Check your internet connection
- Verify the ticker is valid on Yahoo Finance
- Try reducing `max_workers` in `data.py` if running on a slow connection

### Application window is blank after clicking Run

Check the terminal/console for error output. Common causes:
- `claudedev_shared` is not installed or not configured
- The conda environment is not activated
- Holdings data source is unavailable

### Charts don't update after toggling a checkbox

Charts only render after data has been loaded. Click **Run** first, then use toggles.

### Bar chart appears squished or misaligned

Drag the pane dividers to resize. The bar chart pane has the smallest initial weight (6) and may need manual widening on smaller screens.

### Tooltip appears in the wrong position

This can occur with non-standard DPI scaling. The tooltip position is calculated from `widget.winfo_rootx()` and `widget.winfo_rooty()` plus the event coordinates.
