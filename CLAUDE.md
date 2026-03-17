# PnL-Monitor

## Project Overview
Daily portfolio PnL monitor covering a UBS brokerage account and a UBS 401k account. Pulls live holdings from an internal shared library, enriches them with real-time price data from Yahoo Finance, and computes intraday P&L per position and in aggregate.

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
- `concurrent.futures` (stdlib) — used for concurrent ticker fetching

## Dependency File
- `environment.yml` — conda environment definition (Python 3.13, yfinance, pandas)

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

## DataFrame Columns (output of `main.py`)
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

## PnL Summary Output
Per-source PnL printed via `df.groupby('Source')['PnL'].sum()`, followed by total.

## Important Notes
- Use `regular_market_previous_close` (not `previous_close`) for the prior close. `previous_close` includes after-hours prices and gives incorrect results.
- `% Move On Day` is stored as a decimal (not multiplied by 100).
- `PnL = SOD VALUE * % Move On Day` (no division by 100 needed since % Move On Day is decimal).
- Ticker prices are fetched concurrently via `ThreadPoolExecutor` for speed.
- `get_price_data()` is a module-level function (not nested in `__main__`).
- Failed ticker lookups print a warning and return `None` values rather than raising.

## Git
- Always include `.claude/` directory in commits.
- Remote: https://github.com/marange63/PnL-Monitor.git