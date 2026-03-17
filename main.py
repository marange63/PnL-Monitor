from claudedev_shared import ubs_live_price_holdings

if __name__ == '__main__':
    df = ubs_live_price_holdings()
    print(df)