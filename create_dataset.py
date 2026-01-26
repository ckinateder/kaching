from src.downloaders.dataset_downloader import download_full_dataset

if __name__ == "__main__":
    tickers = ["TTD", "DECK"]
    for ticker in tickers:
        df = download_full_dataset(
            ticker=ticker,
            start_date='2024-01-01',
            end_date='2025-12-31',
            output_dir='data/raw',
            check_existing=True
        )