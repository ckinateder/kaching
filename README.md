# KaChing Options Pricing Tool

A semi-automated options pricing tool for the "Weekly Cash KaChing" put spread strategy using empirical P&L distributions from historical options data.

## Project Status

**Current Phase:** Phase 1.1 - Data Foundation

## Installation

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure Theta Data Terminal is running on localhost:25503

## Usage

### Phase 1.1: Download Options Data

```python
from src.data_downloader import ThetaDataDownloader

# Initialize downloader
downloader = ThetaDataDownloader()

# Download options data
df = downloader.download_options_eod_data(
    ticker='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31',
    output_dir='data/raw',
    check_existing=True  # Enables incremental downloads
)

# Save to CSV
df.to_csv('data/raw/AAPL_options_eod.csv', index=False)
```

### Download Stock Prices

Stock prices are needed for OTM% and P&L calculations:

```python
from src.stock_downloader import YFinanceDownloader

# Initialize downloader
downloader = YFinanceDownloader()

# Download stock prices
df = downloader.download_stock_prices(
    ticker='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31',
    output_dir='data/raw',
    check_existing=True  # Enables incremental downloads
)

# Save to CSV
df.to_csv('data/raw/AAPL_stock_prices.csv', index=False)
```

**Stock prices are used for:**
- **OTM% calculation**: `(stock_price_quote_date - strike) / stock_price_quote_date × 100`
- **P&L calculation**: `bid - max(0, strike - stock_price_expiry)`

### Features

**Options Data (ThetaDataDownloader):**
- **Day-by-day download**: Automatically handles API constraint requiring daily requests for `expiration=*`
- **Progress logging**: Real-time feedback on download progress
- **Incremental downloads**: Checks existing CSV files and only downloads missing dates
- **Retry logic**: Exponential backoff for failed requests (3 attempts)
- **Data validation**: Basic sanity checks on downloaded data
- **Essential fields only**: Automatically filters to reduce data redundancy

**Stock Prices (YFinanceDownloader):**
- **Bulk download**: Efficient single API call for entire date range (~150x faster than day-by-day)
- **Incremental downloads**: Checks existing CSV files and only downloads missing dates
- **Retry logic**: Exponential backoff for failed requests (3 attempts)
- **Data validation**: Validates prices and checks for data quality issues
- **Trading days only**: Automatically filters to actual trading days (no weekends/holidays)

### Essential Fields

**Options Data Fields:**

**Contract Info:** symbol, expiration, strike, right
**Temporal:** timestamp
**Pricing:** bid, ask, close
**Volume/Liquidity:** volume, bid_size, ask_size
**Greeks:** delta, theta, vega, implied_vol
**Underlying:** underlying_price, underlying_timestamp

Exotic Greeks and exchange metadata are dropped to minimize storage.

**Stock Price Fields:**

**Identification:** symbol, date
**Pricing:** close (primary), open, high, low, adjusted_close
**Volume:** volume

The `close` field is used for OTM% and P&L calculations. The `adjusted_close` accounts for splits/dividends.

## Data Directory Structure

```
data/
├── raw/                      # Raw downloaded data (Phase 1.1)
│   ├── AAPL_options_eod.csv       # Options data
│   ├── AAPL_stock_prices.csv      # Stock prices
│   ├── MSFT_options_eod.csv
│   ├── MSFT_stock_prices.csv
│   └── ...
└── processed/                # Transformed data (Phase 1.1a - future)
```

## Running Examples

**Options data download:**
```bash
python example_download.py
```

**Stock price download:**
```bash
python example_stock_download.py
```

**Test stock downloader:**
```bash
python test_stock_downloader.py
```

## Project Roadmap

- [x] **Phase 1.1**: Historical data download ← Current
- [ ] **Phase 1.1a**: Data transformation (filter weekly options, calculate OTM%, P&L)
- [ ] **Phase 1.2**: Per-stock aggregation (bucket statistics)
- [ ] **Phase 2**: Core pricing engine
- [ ] **Phase 3**: LLM integration
- [ ] **Phase 4**: User interface
- [ ] **Phase 5**: Validation & refinement

See `kaching-plan.md` for full implementation plan.

## Requirements

- Python 3.12+
- Theta Data Terminal (running on localhost:25503) - for options data
- pandas >= 2.0.0
- requests >= 2.31.0
- yfinance >= 0.2.0 - for stock prices

## License

Private project
