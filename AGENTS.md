# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KaChing is a semi-automated options pricing tool for the "Weekly Cash KaChing" put spread strategy. It uses **empirical P&L distributions** from historical options data rather than predictive modeling. The tool helps select optimal strike prices by analyzing historical performance of similar setups.

**Core Philosophy:** Not predicting "Will SCHW go up?" but answering "When selling 1.5% OTM puts, what was the actual P&L distribution?"

**Current Phase:** Phase 1.1 - Data Foundation (data download infrastructure)

## Python Environment

**CRITICAL:** All Python commands MUST be run within the virtual environment:

```bash
source venv/bin/activate && python <script>
```

Never run `python` or `python3` commands directly without activating venv first.

## Development Commands

### Running Example Scripts
```bash
# Options data download (requires Theta Data Terminal running on localhost:25503)
source venv/bin/activate && python example_options_download.py

# Stock price download
source venv/bin/activate && python example_stock_download.py
```

### Running Tests
```bash
# Test options downloader
source venv/bin/activate && python test_options_downloader.py

# Test stock downloader (comprehensive test suite)
source venv/bin/activate && python test_stock_downloader.py
```

### Dependencies
```bash
# Install/update dependencies
source venv/bin/activate && pip install -r requirements.txt
```

## Architecture

### Module Structure

```
src/
├── __init__.py                    # Package exports (ThetaDataDownloader, YFinanceDownloader)
└── downloaders/                   # Data download modules
    ├── __init__.py               # Downloader exports
    ├── options_downloader.py     # Theta Data API integration
    └── stock_downloader.py       # yfinance integration
```

**Import Pattern:**
- Public API: `from src import ThetaDataDownloader, YFinanceDownloader`
- Direct imports: `from src.downloaders.options_downloader import ThetaDataDownloader`

### Data Flow Architecture

The project follows a phased data pipeline approach:

**Phase 1.1 (Current):** Raw data download
- `ThetaDataDownloader`: Downloads EOD options data from Theta Data Terminal API
- `YFinanceDownloader`: Downloads daily stock prices from yfinance
- Both support incremental downloads (check existing CSV, only fetch missing dates)
- Output: `data/raw/<TICKER>_options_eod.csv` and `data/raw/<TICKER>_stock_prices.csv`

**Phase 1.1a (Future):** Data transformation
- Filter to weekly options only (DTE ≤ 9)
- Calculate OTM% and P&L metrics
- Join stock prices with options data
- Output: `data/processed/` files

**Phase 1.2 (Future):** Per-stock aggregation
- Group by ticker and OTM bucket (0.5% increments)
- Calculate win rates, P&L distributions, confidence metrics
- Create lookup tables for pricing engine

### Key Design Patterns

**1. Downloader Pattern (Both downloaders follow identical interface):**
- Constructor takes minimal config (ThetaDataDownloader takes base_url, YFinanceDownloader none)
- Primary method: `download_*_data(ticker, start_date, end_date, output_dir, check_existing)`
- Always returns DataFrames (never saves directly - caller decides)
- Supports incremental downloads via `check_existing=True`
- Built-in retry logic with exponential backoff (3 attempts)
- Progress logging to stdout

**2. Incremental Download Strategy:**
- If `check_existing=True`, downloaders check for existing CSV in `output_dir`
- Read existing CSV, identify missing dates
- Download only missing dates
- Merge with existing data and return complete DataFrame
- ~150x faster than redownloading (for stock data)

**3. Data Validation:**
- Options: Check for required columns (symbol, expiration, strike, bid, ask, Greeks)
- Stocks: Validate prices > 0, check for data quality issues
- Both filter to essential fields only (drop redundant columns)

## Critical Implementation Details

### Options Downloader (ThetaDataDownloader)

**API Constraint:** Theta Data API requires day-by-day requests when using `expiration=*` (all expirations). The downloader automatically handles this by:
1. Iterating through each date in the range
2. Making individual API calls per date
3. Concatenating results into single DataFrame

**Essential Fields:** Filters to 17 essential columns (see `ESSENTIAL_FIELDS` in `options_downloader.py`):
- Contract info: symbol, expiration, strike, right
- Pricing: bid, ask, close
- Greeks: delta, theta, vega, implied_vol
- Underlying: underlying_price, underlying_timestamp
- Volume: volume, bid_size, ask_size

Exotic Greeks and exchange metadata are dropped to minimize storage.

### Stock Downloader (YFinanceDownloader)

**Bulk Download:** Downloads entire date range in single API call (no day-by-day iteration needed)

**Essential Fields:** Filters to 7 fields (see `STOCK_PRICE_FIELDS` in `stock_downloader.py`):
- Identification: symbol, date
- Pricing: close (PRIMARY), open, high, low, adjusted_close
- Volume: volume

**Usage in Options Analysis:**
- OTM% calculation: `(stock_price_quote_date - strike) / stock_price_quote_date × 100`
- P&L calculation: `bid - max(0, strike - stock_price_expiry)`

### Data Directory Structure

```
data/
├── raw/                          # Phase 1.1 output (current)
│   ├── <TICKER>_options_eod.csv
│   └── <TICKER>_stock_prices.csv
└── processed/                    # Phase 1.1a output (future)
```

## Project Roadmap Context

Understanding where we are vs. where we're going:

**Completed:**
- ✅ Phase 1.1: Historical data download infrastructure

**Next Steps (from kaching-plan.md):**
- Phase 1.1a: Data transformation (filter weekly options, calculate OTM%, P&L)
- Phase 1.2: Per-stock aggregation (bucket statistics)
- Phase 2: Core pricing engine (two modes: full setup vs weekly selection)
- Phase 3: LLM integration (explain recommendations in plain English)
- Phase 4: User interface (CLI tool)
- Phase 5: Validation & refinement

**Two Operating Modes (Future):**
1. **Mode 1: Full Setup** - Initial position (recommends both long put AND weekly short put)
2. **Mode 2: Weekly Selection** - Primary use case (just recommends weekly short put above existing floor)

Mode 2 will be used 95% of the time - quick Thursday morning analysis of multiple active positions.

## External Dependencies

**Theta Data Terminal:**
- Must be running on `localhost:25503` for options data downloads
- Free terminal application (separate from this project)
- API docs: https://docs.thetadata.io/api-reference/option/option-history-eod

**yfinance:**
- No external service needed (queries Yahoo Finance directly)
- Used for stock price data

## Strategy Context

This tool implements the "Weekly Cash KaChing" strategy from the book:
- Sell weekly OTM puts (7-8 DTE)
- Protected by longer-dated long put (90-150 DTE, ~25 delta)
- Weekly premium collection while having defined max risk
- Typical cycle: 16 weeks, rolling long put every ~120 days

The KaChing strategy is a defined-risk options income strategy designed to generate consistent weekly cash flow by selling out-of-the-money put options on stocks exhibiting technical strength. The strategy begins by purchasing a protective long put approximately 5-10% below the current stock price with 90-150 days until expiration (typically around 25 delta). This long put acts as portfolio insurance, capping maximum downside risk regardless of how far the stock falls. With this floor in place, traders then sell weekly put options 7-8 days from expiration at strikes above the protective long put level, collecting immediate premium. The short puts are typically sold 0-3% out-of-the-money, targeting strikes with favorable historical win rates and expected values. This process is repeated weekly throughout the protective put's lifecycle—approximately 16 times over a 120-day period.
The strategy's profitability relies on the statistical fact that roughly 80-85% of options expire worthless, favoring option sellers over buyers. By repeatedly selling weekly puts while protected by the long put floor, traders can collect cumulative premiums that significantly exceed the cost of the protective insurance. For example, collecting $0.95 per contract weekly over 16 weeks yields $15.20 in total premium, while the protective put might cost only $4.20, resulting in an $11.00 net profit per share if all trades expire worthless. Maximum risk per trade is capped at the spread width minus premium collected—typically $2-3 per share—making losses both predictable and manageable. The strategy requires active management and works best on stocks with clear technical "edge" (uptrend or consolidation patterns), as traders must exit positions when the underlying stock loses its favorable technical setup. Success depends on disciplined stock selection, optimal strike pricing based on historical probability distributions, and consistent risk management through proper position sizing and adherence to defined exit rules.

**Critical: The tool does NOT predict stock movement.** It only analyzes historical outcomes for similar setups (e.g., "when selling 1.5% OTM puts on AAPL, here's the win rate and P&L distribution from the past year").

## Common Pitfalls

1. **Don't run Python outside venv** - Always use `source venv/bin/activate && python`
2. **Don't modify downloader return behavior** - They must return DataFrames, not save directly
3. **Don't break incremental download logic** - `check_existing` parameter is critical for efficiency
4. **Don't add fields without updating ESSENTIAL_FIELDS** - Explicitly maintain field lists
5. **Theta Terminal must be running** - Options downloads will fail without it
6. **Respect the phase structure** - Phase 1.1 is ONLY about downloading raw data, not analysis

## File Naming Conventions

- Example scripts: `example_<purpose>_download.py` (e.g., `example_options_download.py`)
- Test scripts: `test_<module>_downloader.py` (e.g., `test_options_downloader.py`)
- Data files: `<TICKER>_<type>.csv` (e.g., `AAPL_options_eod.csv`, `AAPL_stock_prices.csv`)

## References

- Full implementation plan: `kaching-plan.md` (991 lines, comprehensive strategy/architecture)
- Project overview: `README.md` (usage examples, feature list, roadmap)
