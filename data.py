from claudedev_shared import ubs_live_price_holdings, ubs_401k_holdings
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor


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


def load_and_compute(status_cb=None):
    if status_cb:
        status_cb("Loading holdings...")
    df = ubs_live_price_holdings()
    df2 = ubs_401k_holdings()
    df = pd.concat([df, df2], ignore_index=True)

    if status_cb:
        status_cb("Getting prices...")
    tickers = df['Ticker Alias'].tolist()
    with ThreadPoolExecutor() as executor:
        results = dict(zip(tickers, executor.map(get_price_data, tickers)))
    df[['Last Price', 'Last Close', '% Move On Day']] = (
        df['Ticker Alias'].map(results).apply(pd.Series)
    )

    if status_cb:
        status_cb("Calculating PnL...")
    df['PnL'] = df['SOD VALUE'] * df['% Move On Day']

    return df.reset_index(drop=True)
