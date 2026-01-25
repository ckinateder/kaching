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

### Features

- **Day-by-day download**: Automatically handles API constraint requiring daily requests for `expiration=*`
- **Progress logging**: Real-time feedback on download progress
- **Incremental downloads**: Checks existing CSV files and only downloads missing dates
- **Retry logic**: Exponential backoff for failed requests (3 attempts)
- **Data validation**: Basic sanity checks on downloaded data
- **Essential fields only**: Automatically filters to reduce data redundancy

### Essential Fields

The downloader keeps only these essential fields:

**Contract Info:** symbol, expiration, strike, right
**Temporal:** timestamp
**Pricing:** bid, ask, close
**Volume/Liquidity:** volume, bid_size, ask_size
**Greeks:** delta, theta, vega, implied_vol
**Underlying:** underlying_price, underlying_timestamp

Exotic Greeks and exchange metadata are dropped to minimize storage.

## Data Directory Structure

```
data/
├── raw/                      # Raw downloaded data (Phase 1.1)
│   ├── AAPL_options_eod.csv
│   ├── MSFT_options_eod.csv
│   └── ...
└── processed/                # Transformed data (Phase 1.1a - future)
```

## Running Examples

See `example_download.py` for usage examples:

```bash
python example_download.py
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
- Theta Data Terminal (running on localhost:25503)
- pandas >= 2.0.0
- requests >= 2.31.0

## License

Private project
