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
from tqdm import tqdm

import pandas as pd
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from . import (
    validate_date_range,
    generate_date_range,
)
from .base_downloader import BaseDownloader


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


class ThetaDataDownloader(BaseDownloader):
    """
    Download end-of-day options data with Greeks from Theta Data Terminal API.

    Attributes:
        base_url: Base URL for the Theta Data API
        session: Requests session for connection reuse
    """

    def __init__(self, base_url: str = 'http://127.0.0.1:25503/v3', max_workers: int = 8):
        """
        Initialize the Theta Data downloader.

        Args:
            base_url: Base URL for the Theta Data API (default: localhost terminal)
            max_workers: Maximum concurrent workers for parallel downloads (default: 8)
        """
        super().__init__(max_workers=max_workers)
        self.base_url = base_url
        self.session = requests.Session()

    def _download_only(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Download EOD options data with Greeks for all expirations.

        Supports both sequential (max_workers=1) and concurrent (max_workers>1) modes.

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
        total_days = len(all_dates)

        print(f"\nDownloading {ticker} options data for {total_days} days...")

        # Choose execution mode
        if self.max_workers == 1:
            # Sequential mode (original behavior)
            return self._download_sequential(ticker, all_dates, start_date)
        else:
            # Concurrent mode (new behavior)
            return self._download_concurrent(ticker, all_dates, start_date)

    # Abstract method implementations

    def _merge_data(
        self,
        existing_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Delegate to static merge method."""
        return self.merge_options_data(existing_df, new_df)

    def _get_date_column(self) -> str:
        """Return date column name for options data."""
        return 'timestamp'

    def _parse_timestamp(self) -> bool:
        """Options data has timestamp with time component."""
        return True

    def _get_data_type_name(self) -> str:
        """Return human-readable data type name."""
        return 'contracts'

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

    def _download_single_date(
        self,
        ticker: str,
        date: str  # 'YYYY-MM-DD' format
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Download options data for a single date.

        Designed to be called either sequentially or concurrently.

        Args:
            ticker: Stock symbol
            date: Date in 'YYYY-MM-DD' format

        Returns:
            Tuple of (dataframe, error_message)
            - If successful: (df, None)
            - If failed: (None, error_string)
        """
        try:
            # Format date as YYYYMMDD for API
            date_str = pd.to_datetime(date).strftime('%Y%m%d')

            # Build API parameters
            params = {
                'symbol': ticker,
                'expiration': '*',
                'start_date': date_str,
                'end_date': date_str,
                'format': 'csv'
            }

            # Make API request
            response_text = self._make_api_request('/option/history/greeks/eod', params)

            # Parse CSV response
            if response_text and len(response_text.strip()) > 0:
                df = pd.read_csv(StringIO(response_text))

                if not df.empty:
                    # Filter to essential fields
                    essential = self._get_essential_fields()
                    available_fields = [f for f in essential if f in df.columns]
                    df = df[available_fields]

                    # Basic validation
                    if self._validate_data(df):
                        return df, None
                    else:
                        return None, "Data validation failed"
                else:
                    return None, "No data (non-trading day or no options)"
            else:
                return None, "Empty response (non-trading day)"

        except Exception as e:
            error_str = str(e)
            # Check if this is a "no data" error (472)
            if '472' in error_str or 'No data found' in error_str:
                return None, "No data found (API 472)"
            else:
                return None, f"Error: {e}"

    def _download_sequential(
        self,
        ticker: str,
        all_dates: list,
        start_date: str
    ) -> pd.DataFrame:
        """Sequential download mode (original behavior)."""
        all_data = []
        missing_dates = 0

        pbar = tqdm(all_dates, desc=f"{ticker} options", unit="day")
        for date in pbar:
            df, error = self._download_single_date(ticker, date)

            if df is not None:
                all_data.append(df)
            elif error and "No data found (API 472)" in error:
                missing_dates += 1
                pbar.set_postfix(missing=missing_dates, refresh=False)
            elif error:
                tqdm.write(f"[{date}] {error}")

        return self._finalize_download(all_data, ticker, start_date, missing_dates)

    def _download_concurrent(
        self,
        ticker: str,
        all_dates: list,
        start_date: str
    ) -> pd.DataFrame:
        """Concurrent download mode using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_data = []
        missing_dates = 0
        errors = []

        # Create thread pool
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all download tasks
            future_to_date = {
                executor.submit(self._download_single_date, ticker, date): date
                for date in all_dates
            }

            # Process completed downloads as they finish
            with tqdm(total=len(all_dates), desc=f"{ticker} options ({self.max_workers} workers)", unit="day") as pbar:
                for future in as_completed(future_to_date):
                    date = future_to_date[future]

                    try:
                        df, error = future.result()

                        if df is not None:
                            all_data.append(df)
                        elif error:
                            if "No data found (API 472)" in error:
                                missing_dates += 1
                                pbar.set_postfix(missing=missing_dates, refresh=False)
                            else:
                                errors.append((date, error))
                                tqdm.write(f"[{date}] {error}")

                    except Exception as e:
                        errors.append((date, str(e)))
                        tqdm.write(f"[{date}] Unexpected error: {e}")

                    pbar.update(1)

        # Print error summary if any non-trivial errors
        if errors:
            print(f"\n⚠ {len(errors)} dates failed to download:")
            for date, error in errors[:5]:  # Show first 5
                print(f"  - {date}: {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")

        return self._finalize_download(all_data, ticker, start_date, missing_dates)

    def _finalize_download(
        self,
        all_data: list,
        ticker: str,
        start_date: str,
        missing_dates: int
    ) -> pd.DataFrame:
        """
        Finalize download by combining DataFrames and printing summary.

        Shared by both sequential and concurrent modes.
        """
        # Combine all downloaded data
        if not all_data:
            tqdm.write(f"\n⚠ No data downloaded for {ticker}")
            if missing_dates > 0:
                print(f"  Missing dates: {missing_dates}")
            return pd.DataFrame(columns=self._get_essential_fields())

        result_df = pd.concat(all_data, ignore_index=True)

        # Ensure timestamp column is datetime
        result_df['timestamp'] = pd.to_datetime(result_df['timestamp'], format='ISO8601')

        # Sort by expiration, timestamp, strike, right
        result_df = result_df.sort_values(['expiration', 'timestamp', 'strike', 'right'])

        # Remove rows where expiration < start_date
        result_df = result_df[result_df['expiration'] >= start_date]

        print(f"\n✓ Download complete!")
        print(f"  Total contracts: {len(result_df):,}")
        print(f"  Date range: {result_df['timestamp'].min()} to {result_df['timestamp'].max()}")
        print(f"  Unique expirations: {result_df['expiration'].nunique()}")
        if missing_dates > 0:
            print(f"  Missing dates: {missing_dates}")

        return result_df

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
