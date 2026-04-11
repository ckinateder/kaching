import sys
from pathlib import Path

import __init__
from src.downloaders.dataset_downloader import DatasetDownloader
import os
from src.downloaders import get_weekly_options_tickers
from tqdm import tqdm
import random
from time import sleep

if __name__ == "__main__":
    #tickers = ["TTD", "DECK", "MRK"]
    tickers, data = get_weekly_options_tickers()
    
    tickers.remove('VIX')

    random.shuffle(tickers)
    downloader = DatasetDownloader(max_workers=20, rate_limit_delay=0.01)

    print(f"Downloading datasets for {len(tickers)} tickers")
    for i, ticker in enumerate(tickers):
        print(f"Downloading dataset for {ticker} ({i+1}/{len(tickers)})")
        df = downloader.download(
            ticker=ticker,
            start_date='2021-01-01',
            end_date='2026-02-14',
            save=True,
            filepath=os.path.join('data', 'raw', 'dataset', f'{ticker}.parquet'),
            incremental=True
        )
        
        sleep(1)
