"""
Data downloader for Theta Data API.

This module provides functionality to download end-of-day options data with Greeks
from the Theta Data Terminal API.
"""

import time
from io import StringIO
from typing import Optional, Tuple
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from .downloader_utils import (
    validate_date_range,
    generate_date_range,
    find_missing_dates,
    create_output_directory,
    find_contiguous_date_ranges,
    download_and_save_with_incremental
)


# Essential fields to keep (drop unnecessary columns to minimize data redundancy)
ESSENTIAL_FIELDS = [
    # Contract identification
    'symbol',
    'expiration',
    'strike',
    'right',
    'osi_contract_id',  # Computed contract ID: {symbol}{expiration}{right}{strike}

    # Temporal
    'timestamp',  # This is the quote_date

    # Pricing (for P&L calculation)
    'bid',
    'ask',
    'close',  # Actual trade price

    # Volume/Liquidity (for filters)
    'volume',
    'bid_size',
    'ask_size',

    # Greeks (per plan)
    'delta',
    'theta',
    'vega',
    'implied_vol',

    # Underlying data (for OTM% calculation)
    'underlying_price',
    'underlying_timestamp'
]


class ThetaDataDownloader:
    """
    Download end-of-day options data with Greeks from Theta Data Terminal API.

    Attributes:
        base_url: Base URL for the Theta Data API
        session: Requests session for connection reuse
    """

    def __init__(self, base_url: str = 'http://127.0.0.1:25503/v3'):
        """
        Initialize the Theta Data downloader.

        Args:
            base_url: Base URL for the Theta Data API (default: localhost terminal)
        """
        self.base_url = base_url
        self.session = requests.Session()

    def download_options_eod_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Download EOD options data with Greeks for all expirations.

        Pure download function - downloads all dates in range without checking files.
        For incremental downloads, use download_and_save_options_eod_data() instead.

        Downloads data day-by-day (API constraint for expiration=*) with progress logging.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)

        Returns:
            pd.DataFrame with options data for all dates in range

        Raises:
            ValueError: If date format is invalid or end_date < start_date
            Exception: If API requests fail after all retries
        """
        # Validate date inputs
        validate_date_range(start_date, end_date)

        # Generate full date range
        all_dates = generate_date_range(start_date, end_date)

        # Download data day by day
        all_data = []
        total_days = len(all_dates)
        total_contracts = 0

        print(f"\nDownloading {ticker} options data for {total_days} days...")

        for i, date in enumerate(all_dates, 1):
            # Format date as YYYYMMDD for API
            date_str = pd.to_datetime(date).strftime('%Y%m%d')

            # Build API parameters
            params = {
                'symbol': ticker,
                'expiration': '*',  # All expirations
                'start_date': date_str,
                'end_date': date_str,
                'format': 'csv'
            }

            try:
                # Make API request
                response_text = self._make_api_request('/option/history/greeks/eod', params)

                # Parse CSV response
                if response_text and len(response_text.strip()) > 0:
                    df = pd.read_csv(StringIO(response_text))

                    if not df.empty:
                        # Filter to essential fields (only keep columns that exist)
                        essential = self._get_essential_fields()
                        available_fields = [f for f in essential if f in df.columns]
                        df = df[available_fields]

                        # Basic validation
                        if self._validate_data(df):
                            all_data.append(df)
                            total_contracts += len(df)
                            print(f"[{date}] Downloaded {len(df):,} contracts ({i}/{total_days} days)")
                        else:
                            print(f"[{date}] ⚠ Data validation failed, skipping")
                    else:
                        print(f"[{date}] No data (non-trading day or no options)")
                else:
                    print(f"[{date}] Empty response (non-trading day)")

            except Exception as e:
                print(f"[{date}] ✗ Error: {e}")
                print(f"         Skipping this date and continuing...")
                continue

        # Combine all downloaded data
        if not all_data:
            print(f"\n⚠ No data downloaded for {ticker}")
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=self._get_essential_fields())

        result_df = pd.concat(all_data, ignore_index=True)

        # Ensure timestamp column is datetime (for consistent sorting and display)
        result_df['timestamp'] = pd.to_datetime(result_df['timestamp'], format='ISO8601')

        # Sort by expiration date, quote date (timestamp), strike, right
        result_df = result_df.sort_values(['expiration', 'timestamp', 'strike', 'right'])

        # remove rows where expiration date is before the start date
        result_df = result_df[result_df['expiration'] >= start_date]

        print(f"\n✓ Download complete!")
        print(f"  Total contracts: {len(result_df):,}")
        print(f"  Date range: {result_df['timestamp'].min()} to {result_df['timestamp'].max()}")
        print(f"  Unique expirations: {result_df['expiration'].nunique()}")

        return result_df

    def download_and_save_options_eod_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        csv_filepath: str,
        incremental: bool = True
    ) -> pd.DataFrame:
        """
        Download options data and save to CSV (with optional incremental update).

        Convenience function that orchestrates the full workflow.
        See download_and_save_with_incremental() for implementation details.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date 'YYYY-MM-DD'
            end_date: End date 'YYYY-MM-DD'
            csv_filepath: Full path to save CSV (e.g., 'data/raw/AAPL_options_eod.csv')
            incremental: If True, check existing CSV and only download missing dates

        Returns:
            Complete DataFrame (existing + new data)

        Raises:
            ValueError: If date format is invalid or end_date < start_date
            Exception: If API requests fail after all retries
        """
        return download_and_save_with_incremental(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            csv_filepath=csv_filepath,
            incremental=incremental,
            download_func=self.download_options_eod_data,
            merge_func=self.merge_options_data,
            date_column='timestamp',
            parse_timestamp=True,
            data_type_name='contracts',
            essential_fields=self._get_essential_fields()
        )

    def _make_api_request(
        self,
        endpoint: str,
        params: dict,
        max_retries: int = 3,
        initial_backoff: float = 1.0
    ) -> str:
        """
        Make API request with retry logic and exponential backoff.

        Args:
            endpoint: API endpoint path (e.g., '/option/history/greeks/eod')
            params: Query parameters dict
            max_retries: Maximum number of retry attempts
            initial_backoff: Initial backoff time in seconds

        Returns:
            Response text (CSV data)

        Raises:
            Exception if all retries fail
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response.text
                else:
                    error_msg = f"API returned {response.status_code}: {response.text[:200]}"

                    # Don't retry on 4xx client errors (except 429 rate limit)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        raise Exception(error_msg)

                    # Retry on 5xx server errors and 429 rate limit
                    if attempt < max_retries - 1:
                        backoff_time = initial_backoff * (2 ** attempt)
                        print(f"  {error_msg}")
                        print(f"  Retrying in {backoff_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(backoff_time)
                    else:
                        raise Exception(error_msg)

            except (RequestException, Timeout, ConnectionError) as e:
                if attempt < max_retries - 1:
                    backoff_time = initial_backoff * (2 ** attempt)
                    print(f"  Request failed: {e}")
                    print(f"  Retrying in {backoff_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(backoff_time)
                else:
                    raise Exception(f"All {max_retries} attempts failed: {e}")

        raise Exception("API request failed after all retries")

    @staticmethod
    def _get_essential_fields() -> list:
        """Return list of essential field names to keep."""
        return ESSENTIAL_FIELDS

    @staticmethod
    def _validate_data(df: pd.DataFrame) -> bool:
        """
        Perform basic validation on downloaded data.

        Args:
            df: DataFrame to validate

        Returns:
            True if data passes validation, False otherwise
        """
        # Check for required columns
        required_cols = ['symbol', 'expiration', 'strike', 'right', 'timestamp']
        if not all(col in df.columns for col in required_cols):
            print(f"  ⚠ Missing required columns")
            return False

        # Basic sanity checks
        if 'bid' in df.columns and (df['bid'] < 0).any():
            print(f"  ⚠ Found negative bid prices")
            return False

        if 'strike' in df.columns and (df['strike'] <= 0).any():
            print(f"  ⚠ Found non-positive strike prices")
            return False

        if 'volume' in df.columns and (df['volume'] < 0).any():
            print(f"  ⚠ Found negative volume")
            return False

        return True

    @staticmethod
    def merge_options_data(
        existing_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge and deduplicate options data.

        Combines existing and new options data, removes duplicates based on
        contract identification (symbol, expiration, strike, right, timestamp),
        and returns sorted DataFrame.

        Args:
            existing_df: Existing options DataFrame
            new_df: New options DataFrame to merge

        Returns:
            Merged and deduplicated DataFrame, sorted by expiration, timestamp, strike, right
        """
        # Handle empty DataFrames to avoid FutureWarning
        if existing_df.empty and new_df.empty:
            # Both empty - return empty DataFrame with expected columns
            result_df = pd.DataFrame(columns=existing_df.columns if not existing_df.columns.empty else new_df.columns)
        elif existing_df.empty:
            result_df = new_df.copy()
        elif new_df.empty:
            result_df = existing_df.copy()
        else:
            # Concatenate DataFrames
            result_df = pd.concat([existing_df, new_df], ignore_index=True)

        # Early return if result is empty
        if result_df.empty:
            return result_df

        # Remove duplicates (keep most recent)
        result_df = result_df.drop_duplicates(
            subset=['symbol', 'expiration', 'strike', 'right', 'timestamp'],
            keep='last'
        )

        # Ensure timestamp is datetime for consistent sorting
        result_df['timestamp'] = pd.to_datetime(result_df['timestamp'], format='ISO8601')

        # Sort by expiration date, quote date (timestamp), strike, right
        result_df = result_df.sort_values(['expiration', 'timestamp', 'strike', 'right'])

        return result_df
