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
```bash
cd ~/api-thetadata
java -jar ThetaTerminalv3.jar 
```
Make sure your credentials are in the `creds.txt` file in the `api-thetadata` directory.

## Usage

### Phase 1.1: Download Options Data

```python
from src.downloaders.options_downloader import ThetaDataDownloader

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
from src.downloaders.stock_downloader import YFinanceDownloader

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
python example_options_download.py
```

**Stock price download:**
```bash
python example_stock_download.py
```

**Test stock downloader:**
```bash
python test_stock_downloader.py
```

### Running Tests

Run the comprehensive test suite for downloader modules:

```bash
python -m unittest tests/test_downloaders.py
```

The test suite covers:
- Date range validation and generation
- Data merging and deduplication
- Data validation (bad data detection)
- Column standardization
- Dataset joining logic

All tests use real DECK fixtures and don't make any external API calls.

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
