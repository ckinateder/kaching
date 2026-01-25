"""
Combined downloader for both options and stock price data.

This module provides a single function to download both options data and stock prices
for building a complete dataset over a specified date range.
"""

from typing import Optional, Tuple
from pathlib import Path
import pandas as pd

from .options_downloader import ThetaDataDownloader
from .stock_downloader import YFinanceDownloader


def download_full_dataset(
    ticker: str,
    start_date: str,
    end_date: str,
    output_dir: str = 'data/raw',
    check_existing: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Download both options data and stock prices for a ticker over a date range.

    This is the primary function for building a complete dataset for analysis.
    Downloads EOD options data with Greeks and daily stock prices, both supporting
    incremental downloads via CSV checking.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format (inclusive)
        output_dir: Directory to check for existing CSV files (for incremental download)
        check_existing: If True, check existing CSV and only download missing data

    Returns:
        Tuple of (options_df, stock_df) where both are pandas DataFrames

    Raises:
        ValueError: If date format is invalid, end_date < start_date, or invalid ticker
        Exception: If API requests fail after all retries

    Example:
        >>> options_df, stock_df = download_full_dataset(
        ...     ticker='AAPL',
        ...     start_date='2022-01-25',
        ...     end_date='2024-01-25',
        ...     output_dir='data/raw',
        ...     check_existing=True
        ... )
        >>> print(f"Downloaded {len(options_df):,} options contracts and {len(stock_df):,} trading days")
    """
    # Validate date inputs
    try:
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
    except Exception as e:
        raise ValueError(f"Invalid date format. Expected 'YYYY-MM-DD': {e}")

    if end_dt < start_dt:
        raise ValueError(f"end_date ({end_date}) must be >= start_date ({start_date})")

    # Initialize downloaders
    options_downloader = ThetaDataDownloader()
    stock_downloader = YFinanceDownloader()

    # Download options data
    print(f"\n{'='*60}")
    print(f"Downloading dataset for {ticker}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"{'='*60}")

    options_df = options_downloader.download_options_eod_data(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        check_existing=check_existing
    )

    # Download stock prices
    stock_df = stock_downloader.download_stock_prices(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        check_existing=check_existing
    )

    # Final summary
    print(f"\n{'='*60}")
    print(f"Dataset download complete!")
    print(f"{'='*60}")
    print(f"Options data:")
    print(f"  Total contracts: {len(options_df):,}")
    print(f"  Date range: {options_df['timestamp'].min()} to {options_df['timestamp'].max()}")
    print(f"  Unique expirations: {options_df['expiration'].nunique()}")
    print(f"\nStock price data:")
    print(f"  Total trading days: {len(stock_df):,}")
    print(f"  Date range: {stock_df['date'].min()} to {stock_df['date'].max()}")
    print(f"  Price range: ${stock_df['close'].min():.2f} - ${stock_df['close'].max():.2f}")
    print(f"{'='*60}")

    return options_df, stock_df