"""
Shared utility functions for data downloaders.

This module provides common functionality used across multiple downloader classes,
eliminating code duplication and ensuring consistent behavior.
"""

from typing import Optional, Tuple
from pathlib import Path
from tqdm import tqdm

import pandas as pd
import json
import os

def validate_date_range(start_date: str, end_date: str) -> None:
    """
    Validate date range inputs.

    Args:
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format

    Raises:
        ValueError: If date format is invalid or end_date < start_date
    """
    try:
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
    except Exception as e:
        raise ValueError(f"Invalid date format. Expected 'YYYY-MM-DD': {e}")

    if end_dt < start_dt:
        raise ValueError(f"end_date ({end_date}) must be >= start_date ({start_date})")


def generate_date_range(start_date: str, end_date: str) -> list:
    """
    Generate list of dates in 'YYYY-MM-DD' format.

    Args:
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD'

    Returns:
        List of date strings (e.g., ['2024-01-01', '2024-01-02', ...])
    """
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    return [d.strftime('%Y-%m-%d') for d in dates]


def find_missing_dates(
    filepath: str,
    start_date: str,
    end_date: str,
    date_column: str = 'date',
    parse_timestamp: bool = False
) -> Tuple[Optional[pd.DataFrame], list]:
    """
    Check existing Parquet file and identify missing dates.

    Generic function that works for both options and stock data by accepting
    a date_column parameter and optional timestamp parsing.

    Args:
        filepath: Full path to Parquet file (e.g., 'data/raw/AAPL_stock_prices.parquet')
        start_date: Desired start date 'YYYY-MM-DD'
        end_date: Desired end date 'YYYY-MM-DD'
        date_column: Name of column containing dates (default: 'date')
        parse_timestamp: If True, parse datetime column and extract dates
                        (for options data with 'timestamp' column)

    Returns:
        Tuple of (existing_dataframe, list_of_missing_dates)
        If no existing file: (None, all_dates_in_range)
        If all dates exist: (existing_df, [])
    """
    parquet_path = Path(filepath)
    requested_dates = generate_date_range(start_date, end_date)

    # If Parquet file doesn't exist, all dates are missing
    if not parquet_path.exists():
        return None, requested_dates

    try:
        # Load existing Parquet file
        df = pd.read_parquet(filepath)

        if df.empty:
            return None, requested_dates

        # Extract dates from the specified column
        if parse_timestamp:
            # For options data: timestamp column is already datetime from Parquet
            # Just extract dates if needed
            if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
                df[date_column] = pd.to_datetime(df[date_column], format='ISO8601')
            existing_dates = df[date_column].dt.date.unique()
            existing_dates_str = [d.strftime('%Y-%m-%d') for d in existing_dates]
        else:
            # For stock data: use date column directly (already in YYYY-MM-DD format)
            existing_dates_str = df[date_column].unique().tolist()

        # Find missing dates
        missing_dates = [d for d in requested_dates if d not in existing_dates_str]

        return df, missing_dates

    except Exception as e:
        print(f"⚠ Warning: Could not read existing Parquet file: {e}")
        print(f"  Proceeding as if no existing data...")
        return None, requested_dates


def create_output_directory(filepath: str) -> None:
    """
    Create parent directory for output file if it doesn't exist.

    Args:
        filepath: Path to output file
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


def find_contiguous_date_ranges(dates: list, max_gap_days: int = 7) -> list:
    """
    Group a list of date strings into contiguous ranges.

    Takes a list of date strings and returns a list of (start, end) tuples
    representing contiguous date ranges. Small gaps (weekends, holidays) are
    merged to avoid creating too many tiny ranges.

    Args:
        dates: List of date strings in 'YYYY-MM-DD' format (must be sorted)
        max_gap_days: Maximum gap size to merge (default: 7 days for weekends/holidays)
                     Gaps larger than this will create separate ranges.

    Returns:
        List of (start_date, end_date) tuples representing contiguous ranges

    Example:
        >>> dates = ['2024-01-01', '2024-01-02', '2024-01-05', '2024-01-06', '2024-01-07']
        >>> find_contiguous_date_ranges(dates, max_gap_days=7)
        [('2024-01-01', '2024-01-07')]  # Merged because gap is only 2 days
    """
    if not dates:
        return []

    # Convert to datetime for date arithmetic
    date_objects = [pd.to_datetime(d) for d in dates]
    date_objects.sort()

    ranges = []
    range_start = date_objects[0]
    range_end = date_objects[0]

    for i in range(1, len(date_objects)):
        gap_days = (date_objects[i] - date_objects[i-1]).days

        # Merge if gap is small (weekends, holidays) or consecutive
        if gap_days <= max_gap_days:
            # Extend current range
            range_end = date_objects[i]
        else:
            # Large gap found, save current range and start new one
            ranges.append((
                range_start.strftime('%Y-%m-%d'),
                range_end.strftime('%Y-%m-%d')
            ))
            range_start = date_objects[i]
            range_end = date_objects[i]

    # Add the final range
    ranges.append((
        range_start.strftime('%Y-%m-%d'),
        range_end.strftime('%Y-%m-%d')
    ))

    return ranges


def download_and_save_with_incremental(
    ticker: str,
    start_date: str,
    end_date: str,
    filepath: str,
    incremental: bool,
    download_func: callable,
    merge_func: callable,
    date_column: str,
    parse_timestamp: bool,
    data_type_name: str,
    essential_fields: list
) -> pd.DataFrame:
    """
    Generic orchestration function for incremental downloads with Parquet persistence.

    Handles the full workflow:
    1. Check for existing Parquet file (if incremental=True)
    2. Find contiguous ranges of missing dates
    3. Download each range
    4. Merge with existing data
    5. Save to Parquet
    6. Return complete DataFrame

    This function eliminates code duplication between stock and options downloaders
    by accepting function callbacks for download and merge operations.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD'
        filepath: Full path to save Parquet file
        incremental: If True, check existing Parquet file and only download missing dates
        download_func: Function to download data (signature: func(ticker, start, end) -> DataFrame)
        merge_func: Function to merge data (signature: func(existing_df, new_df) -> DataFrame)
        date_column: Column name containing dates in Parquet ('date' or 'timestamp')
        parse_timestamp: Whether to parse datetime column for date extraction
        data_type_name: Name for progress messages ('trading days' or 'contracts')
        essential_fields: List of column names for empty DataFrame fallback

    Returns:
        Complete DataFrame (existing + new data)
    """
    existing_df = None

    if incremental:
        # Check for existing data
        existing_df, missing_dates = find_missing_dates(
            filepath, start_date, end_date,
            date_column=date_column,
            parse_timestamp=parse_timestamp
        )

        if not missing_dates:
            print(f"✓ All data already exists for {ticker} ({start_date} to {end_date})")
            return existing_df

        # Find contiguous ranges of missing dates
        missing_ranges = find_contiguous_date_ranges(missing_dates)

        print(f"Found existing data. Need to download {len(missing_ranges)} date range(s) "
              f"covering {len(missing_dates)} calendar days.")

        # Download each contiguous range separately
        new_data_frames = []
        for range_start, range_end in tqdm(missing_ranges, desc=f"{ticker} download", unit="range"):
            range_df = download_func(ticker, range_start, range_end)
            if not range_df.empty:
                new_data_frames.append(range_df)

        # Combine all downloaded data
        if new_data_frames:
            new_df = pd.concat(new_data_frames, ignore_index=True)
        else:
            new_df = pd.DataFrame(columns=essential_fields)
    else:
        # Non-incremental: download full range
        new_df = download_func(ticker, start_date, end_date)

    # Merge if we have existing data
    if existing_df is not None and not existing_df.empty:
        print(f"\nMerging with existing data ({len(existing_df):,} existing {data_type_name})...")
        result_df = merge_func(existing_df, new_df)
    else:
        result_df = new_df

    # Save to Parquet
    print(f"\nSaving to {filepath}...")
    create_output_directory(filepath)
    result_df.to_parquet(filepath, index=False)
    print(f"✓ Saved {len(result_df):,} {data_type_name}")

    return result_df

def get_weekly_options_tickers(path: str = os.path.join('meta', 'weekly-options-tickers.json')) -> tuple[list, dict]:
    """
    Get list of weekly options tickers.
    """
    with open(path, 'r') as f:
        data = json.load(f)['tickers']

    tickers = [ticker['ticker'] for ticker in data]
    return tickers, data

# Import classes at the end to avoid circular imports
# These imports must come after utility functions are defined
from .base_downloader import BaseDownloader
from .options_downloader import ThetaDataDownloader, ESSENTIAL_FIELDS
from .stock_downloader import YFinanceDownloader, STOCK_PRICE_FIELDS
from .dataset_downloader import DatasetDownloader
