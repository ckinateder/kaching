# KaChing Options Pricing Tool

Semi-automated options pricing for the "Weekly Cash KaChing" put spread strategy using empirical P&L distributions from historical options data.

## Project Status

**Current Phase:** Phase 1.1 - Data Foundation (Download Infrastructure)

- ✅ Options data downloader (Theta Data API)
- ✅ Stock price downloader (yfinance)
- ✅ Combined dataset downloader
- ✅ Concurrent downloads with rate limiting
- ✅ Incremental downloads (skip existing data)
- ✅ Auto-retry for failed requests

**Next:** Phase 1.1a - Data transformation (filter weekly options, calculate OTM%, P&L)

## Quick Start

### Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Start Theta Data Terminal on localhost:25503 (for options data).

### Download Data

```python
from src.downloaders import DatasetDownloader

# Download options + stock data for a ticker
downloader = DatasetDownloader(max_workers=4)  # Concurrent downloads
df = downloader.download(
    ticker='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31',
    save=True,
    filepath='data/raw/AAPL_dataset.parquet',
    incremental=True  # Only download missing dates
)
```

**Performance:** 6-7x faster with concurrent downloads (8 workers default)

### Individual Downloaders

```python
# Options only
from src.downloaders import ThetaDataDownloader
downloader = ThetaDataDownloader()
df = downloader.download('AAPL', '2024-01-01', '2024-12-31')

# Stock prices only
from src.downloaders import YFinanceDownloader
downloader = YFinanceDownloader()
df = downloader.download('AAPL', '2024-01-01', '2024-12-31')
```

## Data Storage

```
data/raw/
├── AAPL_options_eod.parquet    # Options data
├── AAPL_stock_prices.parquet   # Stock prices
├── AAPL_dataset.parquet        # Combined
└── ...
```

## Usage

Download the full dataset for every ticker that supports weekly options. This requires a Theta Data Terminal running on `localhost:25503`.

```python
from src.downloaders.dataset_downloader import DatasetDownloader
from src.postprocess import postprocess_dataset
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
            filepath=os.path.join('data', 'raw', f'{ticker}_dataset.parquet'),
            incremental=True
        )     
```
