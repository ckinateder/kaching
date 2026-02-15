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

## Running Tests

```bash
# Unit tests
python -m unittest tests/test_downloaders.py

# Performance comparison
python test_concurrent_download.py
```

## Roadmap

- [x] Phase 1.1: Data download infrastructure
- [ ] Phase 1.1a: Transform data (weekly options, OTM%, P&L)
- [ ] Phase 1.2: Aggregation & statistics
- [ ] Phase 2: Pricing engine
- [ ] Phase 3: LLM explanations
- [ ] Phase 4: CLI interface

See `kaching-plan.md` for details.

## Requirements

- Python 3.12+
- Theta Data Terminal (localhost:25503)
- Dependencies: pandas, requests, yfinance, tqdm
