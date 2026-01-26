"""
Stock price data downloader using yfinance API.

This module provides functionality to download daily stock price data
for use in options analysis (OTM% and P&L calculations).
"""

import time
from typing import Optional, Tuple
from pathlib import Path

import pandas as pd
import yfinance as yf


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
        end_date: str,
        output_dir: str = 'data/raw',
        check_existing: bool = True
    ) -> pd.DataFrame:
        """
        Download daily stock prices for a ticker.

        Downloads stock price data in a single bulk API call (much faster than
        day-by-day downloads). Supports incremental downloads by checking existing
        CSV files.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)
            output_dir: Directory to check for existing CSV (for incremental download)
            check_existing: If True, check existing CSV and only download missing dates

        Returns:
            pd.DataFrame with daily stock prices

        Raises:
            ValueError: If date format is invalid, end_date < start_date, or invalid ticker
            Exception: If API requests fail after all retries
        """
        # Validate date inputs
        try:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
        except Exception as e:
            raise ValueError(f"Invalid date format. Expected 'YYYY-MM-DD': {e}")

        if end_dt < start_dt:
            raise ValueError(f"end_date ({end_date}) must be >= start_date ({start_date})")

        # Check for existing data and identify missing dates
        existing_df = None
        download_start = start_date
        download_end = end_date

        if check_existing:
            existing_df, missing_dates = self._check_existing_data(
                ticker, start_date, end_date, output_dir
            )

            if not missing_dates:
                print(f"✓ All data already exists for {ticker} ({start_date} to {end_date})")
                return existing_df

            print(f"Found existing data. Need to download {len(missing_dates)} missing dates.")

            # Find min/max of missing dates to create contiguous range
            download_start = min(missing_dates)
            download_end = max(missing_dates)

            print(f"Downloading missing range: {download_start} to {download_end}")

        # Download stock prices
        print(f"\nDownloading {ticker} stock prices from {download_start} to {download_end}...")

        new_df = self._download_with_retry(ticker, download_start, download_end)

        if new_df.empty:
            print(f"\n⚠ No data downloaded for {ticker}")
            if existing_df is not None and not existing_df.empty:
                return existing_df
            return pd.DataFrame(columns=self._get_essential_fields())

        # If we had existing data and did incremental download, filter to only missing dates
        if check_existing and existing_df is not None:
            # Filter new data to only actually missing dates
            new_df = new_df[new_df['date'].isin(missing_dates)]

            # Merge with existing
            result_df = pd.concat([existing_df, new_df], ignore_index=True)
            result_df = result_df.sort_values('date')
            result_df = result_df.drop_duplicates(['symbol', 'date'], keep='last')
        else:
            result_df = new_df

        print(f"\n✓ Download complete!")
        print(f"  Trading days: {len(result_df):,}")
        print(f"  Date range: {result_df['date'].min()} to {result_df['date'].max()}")
        print(f"  Price range: ${result_df['close'].min():.2f} - ${result_df['close'].max():.2f}")

        return result_df

    def _check_existing_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        output_dir: str
    ) -> Tuple[Optional[pd.DataFrame], list]:
        """
        Check for existing CSV and identify missing dates.

        Args:
            ticker: Stock symbol
            start_date: Desired start date 'YYYY-MM-DD'
            end_date: Desired end date 'YYYY-MM-DD'
            output_dir: Directory where CSV might exist

        Returns:
            Tuple of (existing_dataframe, list_of_missing_dates)
            If no existing file, returns (None, all_dates_in_range)
        """
        # Build expected CSV path
        csv_path = Path(output_dir) / f"{ticker}_stock_prices.csv"

        # Generate requested date range (all calendar days)
        requested_dates = self._generate_date_range(start_date, end_date)

        # If CSV doesn't exist, all dates are missing
        if not csv_path.exists():
            return None, requested_dates

        try:
            # Load existing CSV
            df = pd.read_csv(csv_path)

            if df.empty:
                return None, requested_dates

            # Get existing dates (already in YYYY-MM-DD format)
            existing_dates = df['date'].unique().tolist()

            # Find missing dates
            missing_dates = [d for d in requested_dates if d not in existing_dates]

            return df, missing_dates

        except Exception as e:
            print(f"⚠ Warning: Could not read existing CSV: {e}")
            print(f"  Proceeding as if no existing data...")
            return None, requested_dates

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
    def _generate_date_range(start_date: str, end_date: str) -> list:
        """
        Generate list of dates in 'YYYY-MM-DD' format.

        Args:
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'

        Returns:
            List of date strings
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        return [d.strftime('%Y-%m-%d') for d in dates]
