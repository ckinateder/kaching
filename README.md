# KaChing Options Pricing Tool

Semi-automated options pricing for the "Weekly Cash KaChing" put spread strategy using empirical P&L distributions from historical options data.

**Core Philosophy:** Not predicting "Will SCHW go up?" but answering "When selling 1.5% OTM puts, what was the actual P&L distribution?"

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Options data requires Theta Data Terminal running on `localhost:25503`.

## Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `scripts/create_dataset.py` | Download datasets for all weekly options tickers | `data/raw/dataset/*.parquet` |
| `scripts/macro_summary.py` | Generate summary stats + composite scores across all tickers | `outputs/macro_summary.csv`, `outputs/kaching_scored_stocks.csv` |
| `scripts/main.py` | Analyze a single ticker with visualizations | `img/<TICKER>_bucket_analysis.png`, `data/processed/<TICKER>_filtered_dataset.csv` |

```bash
# Download all data (requires Theta Terminal)
python scripts/create_dataset.py

# Score all tickers
python scripts/macro_summary.py

# Analyze a single ticker
python scripts/main.py --ticker AAPL
```

## Architecture

```
src/
├── downloaders/
│   ├── options_downloader.py    # Theta Data API (EOD options, day-by-day)
│   ├── stock_downloader.py      # yfinance (bulk daily prices)
│   └── dataset_downloader.py   # Combined downloader with concurrent workers
└── postprocess/
    └── __init__.py              # Filtering, P&L calc, OTM bucketing
```

```
data/
├── raw/
│   ├── dataset/    # Combined parquet files (options + stock joined)
│   ├── option/     # Raw options contracts
│   └── stock/      # Daily stock prices
└── processed/      # Filtered per-ticker CSVs

outputs/
├── macro_summary.csv            # Per-ticker stats (IV, best bucket, P&L, spread)
└── kaching_scored_stocks.csv    # Ranked + tiered stock universe (A/B/C)
```

## Scoring

`macro_summary.py` runs two passes:

1. **Macro summary** — for each ticker, finds the OTM bucket with highest avg P&L and computes stats
2. **Composite score** — ranks the filtered universe by a weighted signal:
   - 50% avg P&L% in best bucket
   - 30% liquidity (quote count)
   - 20% spread (inverted — lower is better)

Hard filters before scoring: `best_bucket_count >= 10`, `$3 <= price <= $300`, `avg_pnl_pct > 0`.

Tiers: **A** = top 15%, **B** = top 50%, **C** = rest.

## OTM Buckets

Options are grouped into 0.5% increments: `0.0-0.5%`, `0.5-1.0%`, ..., `4.5-5.0%` OTM.

Filter criteria for weekly puts: PUT only, Thu/Fri quote dates, DTE 6-9, bid > 0, deduped per (date, strike, expiry).

## Strategy Context

Implements the "Weekly Cash KaChing" strategy:
- Sell weekly OTM puts (7-8 DTE)
- Protected by longer-dated long put (90-150 DTE, ~25 delta)
- Typical cycle: 16 weeks, rolling long put every ~120 days
