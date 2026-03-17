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


if __name__ == '__main__':
    df = ubs_live_price_holdings()
    df2 = ubs_401k_holdings()
    df = pd.concat([df, df2], ignore_index=True)

    print("Getting Prices")
    tickers = df['Ticker Alias'].tolist()
    with ThreadPoolExecutor() as executor:
        results = dict(zip(tickers, executor.map(get_price_data, tickers)))
    df[['Last Price', 'Last Close', '% Move On Day']] = df['Ticker Alias'].map(results).apply(pd.Series)

    print("Calculating PnL")
    df['PnL'] = df['SOD VALUE'] * df['% Move On Day']

    summary = df.groupby('Source')['PnL'].sum()
    for source, pnl in summary.items():
        print(f"{source} PnL: ${pnl:,.2f}")
    print(f"Total PnL: ${df['PnL'].sum():,.2f}")
