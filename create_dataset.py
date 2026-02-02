from src.downloaders.dataset_downloader import download_full_dataset
from src.postprocess import add_moneyness_column, add_price_at_expiry, calculate_pnl
import os

if __name__ == "__main__":
    tickers = ["TTD", "DECK"]
    for ticker in tickers:
        df = download_full_dataset(
            ticker=ticker,
            start_date='2025-12-01',
            end_date='2025-12-31',
        )
        
        # add moneyness column
        df = add_moneyness_column(df)

        # add price at expiry
        df = add_price_at_expiry(df)

        # calculate pnl
        df = calculate_pnl(df)

        # only keep puts
        df = df[df['right'] == 'PUT']

        # -   restrict to moneyness<0 and moneyness>-0.1
        df = df[(df['moneyness'] < 0) & (df['moneyness'] > -0.1)]

        # save to csv
        if not os.path.exists(os.path.join('data', 'processed')):
            os.makedirs(os.path.join('data', 'processed'))
        df.to_csv(os.path.join('data', 'processed', f'{ticker}_dataset.csv'), index=False)
        print(f"Saved {ticker} dataset to {os.path.join('data', 'processed', f'{ticker}_dataset.csv')}")