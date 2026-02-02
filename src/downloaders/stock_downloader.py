"""
Stock price data downloader using yfinance API.

This module provides functionality to download daily stock price data
for use in options analysis (OTM% and P&L calculations).
"""

import time

import pandas as pd
import yfinance as yf

from . import (
    validate_date_range,
    download_and_save_with_incremental
)


# Essential fields to keep for stock price data
STOCK_PRICE_FIELDS = [
    'symbol',           # Ticker symbol
    'date',            # Trading date
    'close',           # Closing price (PRIMARY - used for OTM% and P&L)
    'open',            # Opening price
    'high',            # Daily high
    'low',             # Daily low
    'volume',          # Trading volume
    'adjusted_close'   # Adjusted for splits/dividends
]


class YFinanceDownloader:
    """
    Download daily stock price data using yfinance.

    This downloader follows the same patterns as ThetaDataDownloader:
    - Returns DataFrames (never saves directly)
    - Supports incremental downloads via CSV checking
    - Retry logic with exponential backoff
    - Progress logging
    - Data validation
    - Graceful error handling
    """

    def __init__(self):
        """Initialize the yfinance downloader."""
        pass

    def download_stock_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Download daily stock prices for a ticker.

        Pure download function - downloads all dates in range without checking files.
        For incremental downloads, use download_and_save_stock_prices() instead.

        Downloads stock price data in a single bulk API call (much faster than
        day-by-day downloads).

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)

        Returns:
            pd.DataFrame with daily stock prices

        Raises:
            ValueError: If date format is invalid, end_date < start_date, or invalid ticker
            Exception: If API requests fail after all retries
        """
        # Validate date inputs
        validate_date_range(start_date, end_date)

        # Download stock prices
        print(f"\nDownloading {ticker} stock prices from {start_date} to {end_date}...")

        result_df = self._download_with_retry(ticker, start_date, end_date)

        if result_df.empty:
            print(f"\n⚠ No data downloaded for {ticker}")
            return pd.DataFrame(columns=self._get_essential_fields())

        print(f"\n✓ Download complete!")
        print(f"  Trading days: {len(result_df):,}")
        print(f"  Date range: {result_df['date'].min()} to {result_df['date'].max()}")
        print(f"  Price range: ${result_df['close'].min():.2f} - ${result_df['close'].max():.2f}")

        return result_df

    def download_and_save_stock_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        csv_filepath: str,
        incremental: bool = True
    ) -> pd.DataFrame:
        """
        Download stock prices and save to CSV (with optional incremental update).

        Convenience function that orchestrates the full workflow.
        See download_and_save_with_incremental() for implementation details.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
            csv_filepath: Full path to save CSV (e.g., 'data/raw/AAPL_stock_prices.csv')
            incremental: If True, check existing CSV and only download missing dates

        Returns:
            Complete DataFrame (existing + new data)

        Raises:
            ValueError: If date format is invalid, end_date < start_date, or invalid ticker
            Exception: If API requests fail after all retries
        """
        return download_and_save_with_incremental(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            csv_filepath=csv_filepath,
            incremental=incremental,
            download_func=self.download_stock_prices,
            merge_func=self.merge_stock_data,
            date_column='date',
            parse_timestamp=False,
            data_type_name='trading days',
            essential_fields=self._get_essential_fields()
        )

    def _download_with_retry(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        max_retries: int = 3,
        initial_backoff: float = 1.0
    ) -> pd.DataFrame:
        """
        Download stock prices with retry logic and exponential backoff.

        Args:
            ticker: Stock symbol
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds

        Returns:
            DataFrame with stock prices

        Raises:
            ValueError: If ticker is invalid
            Exception: If all retries fail
        """
        for attempt in range(max_retries):
            try:
                # Create ticker object
                ticker_obj = yf.Ticker(ticker)

                # Download historical data
                # yfinance expects end_date to be exclusive, so add 1 day
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                end_date_adjusted = end_dt.strftime('%Y-%m-%d')

                df = ticker_obj.history(start=start_date, end=end_date_adjusted)

                # Check if we got any data
                if df.empty:
                    # Check if ticker is valid by trying to get info
                    info = ticker_obj.info
                    if not info or 'symbol' not in info:
                        raise ValueError(f"Invalid ticker: {ticker}")

                    # Valid ticker but no data for this date range
                    print(f"  ⚠ No trading data available for {ticker} in this date range")
                    return pd.DataFrame(columns=self._get_essential_fields())

                # Standardize columns to match our schema
                df = self._standardize_columns(df, ticker)

                # Validate data
                if not self._validate_data(df):
                    raise Exception("Data validation failed")

                print(f"✓ Downloaded {len(df)} trading days")
                print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
                print(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

                return df

            except ValueError as e:
                # Don't retry on invalid ticker
                raise e

            except Exception as e:
                if attempt < max_retries - 1:
                    backoff_time = initial_backoff * (2 ** attempt)
                    print(f"  Download failed: {e}")
                    print(f"  Retrying in {backoff_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(backoff_time)
                else:
                    raise Exception(f"All {max_retries} attempts failed: {e}")

        raise Exception("Download failed after all retries")

    def _standardize_columns(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """
        Standardize yfinance column names to match our schema.

        yfinance returns columns: Open, High, Low, Close, Volume, Dividends, Stock Splits
        We need: symbol, date, close, open, high, low, volume, adjusted_close

        Args:
            df: Raw DataFrame from yfinance
            ticker: Stock symbol to add

        Returns:
            DataFrame with standardized columns
        """
        # Reset index to make date a column
        df = df.reset_index()

        # Rename columns to lowercase with underscores
        column_mapping = {
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',  # yfinance 'Close' is already adjusted
            'Volume': 'volume'
        }

        df = df.rename(columns=column_mapping)

        # Add symbol column
        df['symbol'] = ticker

        # Format date as YYYY-MM-DD string
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

        # Filter to essential fields (only keep columns that exist)
        essential = self._get_essential_fields()
        available_fields = [f for f in essential if f in df.columns]
        df = df[available_fields]

        return df

    def _validate_data(self, df: pd.DataFrame) -> bool:
        """
        Perform basic validation on downloaded stock price data.

        Args:
            df: DataFrame to validate

        Returns:
            True if data passes validation, False otherwise
        """
        # Check for required columns
        required_cols = ['symbol', 'date', 'close']
        if not all(col in df.columns for col in required_cols):
            print(f"  ⚠ Missing required columns: {required_cols}")
            return False

        # Check for positive prices
        if (df['close'] <= 0).any():
            print(f"  ⚠ Found non-positive closing prices")
            return False

        # Check for large gaps in dates (> 14 calendar days ~ 10 trading days)
        df_sorted = df.sort_values('date')
        if len(df_sorted) > 1:
            date_diffs = pd.to_datetime(df_sorted['date']).diff().dt.days
            max_gap = date_diffs.max()
            if pd.notna(max_gap) and max_gap > 14:
                print(f"  ⚠ Warning: Large date gap found ({max_gap} days) - possible delisting/halt")
                # Don't fail validation, just warn

        return True

    @staticmethod
    def _get_essential_fields() -> list:
        """Return list of essential field names to keep."""
        return STOCK_PRICE_FIELDS

    @staticmethod
    def merge_stock_data(
        existing_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge and deduplicate stock data.

        Combines existing and new stock price data, removes duplicates based on
        symbol and date, and returns sorted DataFrame.

        Args:
            existing_df: Existing stock prices DataFrame
            new_df: New stock prices DataFrame to merge

        Returns:
            Merged and deduplicated DataFrame, sorted by date
        """
        # Concatenate DataFrames
        result_df = pd.concat([existing_df, new_df], ignore_index=True)

        # Sort by date
        result_df = result_df.sort_values('date')

        # Remove duplicates (keep most recent)
        result_df = result_df.drop_duplicates(['symbol', 'date'], keep='last')

        return result_df
