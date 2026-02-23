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

When `save=True`, `DatasetDownloader` writes three files automatically:

```
data/raw/
├── dataset/AAPL.parquet   # Combined (options + stock prices joined)
├── option/AAPL.parquet    # Raw options contracts
└── stock/AAPL.parquet     # Daily stock prices
```

```python
from src.downloaders import DatasetDownloader

downloader = DatasetDownloader(max_workers=8)
df = downloader.download(
    ticker='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31',
    save=True,
    filepath='data/raw/dataset/AAPL.parquet',
    incremental=True  # Only downloads missing dates
)
```

**Performance:** 6-7x faster with concurrent downloads (8 workers default)

Incremental state is tracked independently per folder — on subsequent runs, `option/` and `stock/` are updated with only new dates, and the `dataset/` file is rebuilt from the full joined data (join is fast; API calls are what's slow).

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

## Usage

Download the full dataset for every ticker that supports weekly options. This requires a Theta Data Terminal running on `localhost:25503`.

```bash
python create_dataset.py
```
