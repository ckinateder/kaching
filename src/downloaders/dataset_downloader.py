"""
Combined downloader for both options and stock price data.

This module provides a single function to download both options data and stock prices
for building a complete dataset over a specified date range.
"""

from typing import Optional
from pathlib import Path
import pandas as pd

from .options_downloader import ThetaDataDownloader
from .stock_downloader import YFinanceDownloader
from . import validate_date_range


def download_full_dataset(
    ticker: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Download both options data and stock prices for a ticker over a date range,
    and combine them into a single DataFrame.

    This is the primary function for building a complete dataset for analysis.
    Downloads EOD options data with Greeks and daily stock prices, both supporting
    incremental downloads via CSV checking, then joins them together.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format (inclusive)
        output_dir: Directory to check for existing CSV files (for incremental download)
        check_existing: If True, check existing CSV and only download missing data

    Returns:
        Combined DataFrame with all options data and corresponding stock prices.
        Contains both options columns and stock price columns.

    Raises:
        ValueError: If date format is invalid, end_date < start_date, or invalid ticker
        Exception: If API requests fail after all retries

    Example:
        >>> df = download_full_dataset(
        ...     ticker='AAPL',
        ...     start_date='2022-01-25',
        ...     end_date='2024-01-25',
        ...     output_dir='data/raw',
        ...     check_existing=True
        ... )
        >>> print(f"Downloaded {len(df):,} combined records")
        >>> print(df.columns.tolist())
        # ['symbol', 'expiration', 'strike', 'right', 'delta', 'theta', ...,
        #  'open', 'high', 'low', 'volume', 'adjusted_close', ...]
    """
    # Validate date inputs
    validate_date_range(start_date, end_date)

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
    )

    # Download stock prices
    stock_df = stock_downloader.download_stock_prices(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
    )

    # Convert both to datetime for proper joining
    options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
    options_df['expiration'] = pd.to_datetime(options_df['expiration'])
    stock_df['date'] = pd.to_datetime(stock_df['date'])

    # add "underlying_" prefix to stock_df columns
    stock_df.columns = [f'underlying_{col}' for col in stock_df.columns]

    # Extract date part for matching (same calendar day, regardless of time)
    options_df['timestamp_date'] = options_df['timestamp'].dt.date
    stock_df['underlying_date_date'] = stock_df['underlying_date'].dt.date

    # Left join: preserve all options data, add stock prices where available
    # Match on same calendar day (options timestamp and stock date)
    combined_df = options_df.merge(
        stock_df,
        left_on='timestamp_date',
        right_on='underlying_date_date',
        how='left',
    )

    # Clean up: drop temporary date columns and stock identifier columns
    combined_df = combined_df.drop(columns=['timestamp_date', 'underlying_date_date', 'underlying_symbol'])

    # Round price columns to 2 decimal places
    price_cols = ['underlying_open', 'underlying_high', 'underlying_low', 'underlying_close']
    combined_df[price_cols] = combined_df[price_cols].round(2)

    # Final summary
    print(f"\n{'='*60}")
    print(f"Dataset download complete!")
    print(f"{'='*60}")
    print(f"Combined data:")
    print(f"  Total records: {len(combined_df):,}")
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  Unique expirations: {combined_df['expiration'].nunique()}")
    print(f"  Stock price columns: {[col for col in combined_df.columns if col not in options_df.columns]}")
    print(f"{'='*60}")

    return combined_df

if __name__ == "__main__":
    tickers = ["TTD", "DECK"]
    for ticker in tickers:
        df = download_full_dataset(
            ticker=ticker,
            start_date='2025-12-01',
            end_date='2025-12-31',
        )
