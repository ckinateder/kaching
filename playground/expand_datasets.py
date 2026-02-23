"""
Migration script: split flat data/raw/<TICKER>_dataset.parquet files into 3-folder structure.

Usage:
    # Dry-run (default) - shows what would be created
    python expand_datasets.py

    # Process a single ticker (dry-run)
    python expand_datasets.py --ticker AAPL

    # Execute migration for all tickers
    python expand_datasets.py --execute

    # Execute migration for a single ticker
    python expand_datasets.py --ticker AAPL --execute
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

RAW_DIR = Path('data/raw')
DATASET_DIR = RAW_DIR / 'dataset'
OPTION_DIR  = RAW_DIR / 'option'
STOCK_DIR   = RAW_DIR / 'stock'

STOCK_RENAME = {
    'underlying_date':           'date',
    'underlying_close':          'close',
    'underlying_open':           'open',
    'underlying_high':           'high',
    'underlying_low':    'low',
    'underlying_volume': 'volume',
}


def split_dataset(df: pd.DataFrame, ticker: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a combined dataset DataFrame into options and stock DataFrames."""
    # Options: all columns that don't start with 'underlying_'
    options_cols = [c for c in df.columns if not c.startswith('underlying_')]
    options_df = df[options_cols].drop_duplicates()

    # Stock: underlying_* columns → renamed, deduplicated by date
    stock_source_cols = [c for c in STOCK_RENAME if c in df.columns]
    stock_df = (
        df[stock_source_cols]
        .dropna(subset=['underlying_date'])
        .drop_duplicates(subset=['underlying_date'])
        .rename(columns=STOCK_RENAME)
        .reset_index(drop=True)
    )
    stock_df.insert(0, 'symbol', ticker)
    stock_df['date'] = pd.to_datetime(stock_df['date']).dt.strftime('%Y-%m-%d')

    return options_df, stock_df


def validate_split(
    original_df: pd.DataFrame,
    options_df: pd.DataFrame,
    stock_df: pd.DataFrame,
) -> bool:
    """Run post-split validation. Returns True if all checks pass."""
    passed = True
    expected_options_rows = len(original_df.drop_duplicates(
        subset=[c for c in original_df.columns if not c.startswith('underlying_')]
    ))

    checks = [
        (
            len(options_df) == expected_options_rows,
            f"options rows: got {len(options_df)}, expected {expected_options_rows}"
        ),
        (
            len(stock_df) == original_df['underlying_date'].nunique(),
            f"stock rows: got {len(stock_df)}, expected {original_df['underlying_date'].nunique()} unique dates"
        ),
        (
            all(c in options_df.columns for c in [c for c in original_df.columns if not c.startswith('underlying_')]),
            "options columns mismatch"
        ),
        (
            all(c in stock_df.columns for c in ['symbol'] + [STOCK_RENAME[c] for c in STOCK_RENAME if c in original_df.columns]),
            f"stock columns mismatch: {[STOCK_RENAME[c] for c in STOCK_RENAME if c in original_df.columns and STOCK_RENAME[c] not in stock_df.columns]}"
        ),
    ]

    for ok, msg in checks:
        status = "PASS" if ok else "FAIL"
        print(f"    [{status}] {msg}")
        if not ok:
            passed = False

    return passed


def find_flat_parquets(ticker: str = None) -> list[Path]:
    """Find flat data/raw/<TICKER>_dataset.parquet files (not in subdirectories)."""
    if ticker:
        candidates = [RAW_DIR / f'{ticker}_dataset.parquet']
    else:
        candidates = [p for p in RAW_DIR.glob('*_dataset.parquet') if p.parent == RAW_DIR]
    return [p for p in candidates if p.exists()]


def process_ticker(source_path: Path, execute: bool) -> bool:
    """Process a single flat parquet file. Returns True on success."""
    ticker = source_path.stem.replace('_dataset', '')

    dataset_out = DATASET_DIR / f'{ticker}.parquet'
    option_out  = OPTION_DIR  / f'{ticker}.parquet'
    stock_out   = STOCK_DIR   / f'{ticker}.parquet'

    # Skip if all outputs already exist
    all_exist = all(p.exists() for p in [dataset_out, option_out, stock_out])
    if all_exist:
        print(f"  [SKIP] {ticker} — all 3 output files already exist")
        return True

    df = pd.read_parquet(source_path)
    options_df, stock_df = split_dataset(df, ticker)

    print(f"  {ticker}: {len(df):,} rows → {len(options_df):,} options rows, {len(stock_df):,} stock rows")

    if not validate_split(df, options_df, stock_df):
        print(f"  [ABORT] Validation failed for {ticker}")
        return False

    if execute:
        for out_dir in [DATASET_DIR, OPTION_DIR, STOCK_DIR]:
            out_dir.mkdir(parents=True, exist_ok=True)

        options_df.to_parquet(option_out, index=False)
        stock_df.to_parquet(stock_out, index=False)
        # Copy the original combined dataset to the new location
        df.to_parquet(dataset_out, index=False)
        print(f"  [DONE] Written: {option_out}, {stock_out}, {dataset_out}")
    else:
        print(f"  [DRY-RUN] Would write: {option_out}, {stock_out}, {dataset_out}")

    return True


def main():
    parser = argparse.ArgumentParser(description='Migrate flat dataset parquets to 3-folder structure')
    parser.add_argument('--ticker', help='Process a single ticker (default: all)')
    parser.add_argument('--execute', action='store_true', help='Write output files (default: dry-run)')
    args = parser.parse_args()

    sources = find_flat_parquets(args.ticker)
    if not sources:
        print(f"No flat dataset parquets found in {RAW_DIR}")
        sys.exit(0)

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"\n[{mode}] Processing {len(sources)} ticker(s)...\n")

    failed = []
    for source in tqdm(sources, desc="Migrating", unit="ticker"):
        ok = process_ticker(source, execute=args.execute)
        if not ok:
            failed.append(source.stem)

    print(f"\n{'='*50}")
    print(f"Done. {len(sources) - len(failed)}/{len(sources)} succeeded.")
    if failed:
        print(f"Failed: {failed}")
        sys.exit(1)


if __name__ == '__main__':
    main()
