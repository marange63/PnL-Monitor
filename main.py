from claudedev_shared import ubs_live_price_holdings
import yfinance as yf

if __name__ == '__main__':
    df = ubs_live_price_holdings()

    def get_daily_pct_move(ticker):
        try:
            data = yf.Ticker(ticker).fast_info
            return round((data.last_price - data.previous_close) / data.previous_close * 100, 2)
        except Exception:
            return None

    df['% Move On Day'] = df['Ticker Alias'].apply(get_daily_pct_move)
    print(df)