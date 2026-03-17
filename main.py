from claudedev_shared import ubs_live_price_holdings
import yfinance as yf
import pandas as pd

if __name__ == '__main__':
    df = ubs_live_price_holdings()

    def get_price_data(ticker):
        try:
            data = yf.Ticker(ticker).fast_info
            last_price = data.last_price
            last_close = data.regular_market_previous_close
            pct_move = (last_price - last_close) / last_close
            return last_price, last_close, pct_move
        except Exception:
            return None, None, None

    df[['Last Price', 'Last Close', '% Move On Day']] = df['Ticker Alias'].apply(
        lambda t: get_price_data(t)
    ).apply(pd.Series)
    df['PnL'] = df['SOD VALUE'] * df['% Move On Day']
    print(df)