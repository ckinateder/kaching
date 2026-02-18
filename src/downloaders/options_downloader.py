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

    def __init__(
        self,
        base_url: str = 'http://127.0.0.1:25503/v3',
        max_workers: int = 8,
        rate_limit_delay: float = 0.1
    ):
        """
        Initialize the Theta Data downloader.

        Args:
            base_url: Base URL for the Theta Data API (default: localhost terminal)
            max_workers: Maximum concurrent workers for parallel downloads (default: 8)
            rate_limit_delay: Minimum delay between requests in seconds (default: 0.1 = 10 req/s)
                             Set to 0 to disable rate limiting
        """
        super().__init__(max_workers=max_workers)
        self.base_url = base_url
        self.session = requests.Session()
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0
        self._request_lock = None  # Will be initialized in concurrent mode

    def _download_only(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        dates_to_download: Optional[list] = None
    ) -> pd.DataFrame:
        """
        Download EOD options data with Greeks for all expirations.

        Supports both sequential (max_workers=1) and concurrent (max_workers>1) modes.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)
            dates_to_download: Optional list of specific dates to download in 'YYYY-MM-DD' format.
                             If provided, only these dates will be downloaded (ignoring start_date/end_date range).
                             If None, downloads all dates in the start_date to end_date range.

        Returns:
            pd.DataFrame with options data for all dates in range

        Raises:
            ValueError: If date format is invalid or end_date < start_date
            Exception: If API requests fail after all retries
        """
        # If specific dates provided, use those; otherwise use full range
        if dates_to_download:
            all_dates = dates_to_download
        else:
            # Validate date inputs
            validate_date_range(start_date, end_date)
            # Generate full date range
            all_dates = generate_date_range(start_date, end_date)

        total_days = len(all_dates)
        print(f"\nDownloading {ticker} options data for {total_days} days...")

        # Choose execution mode
        # Use start_date from first date in all_dates for filtering (needed for _finalize_download)
        first_date = all_dates[0] if all_dates else start_date
        if self.max_workers == 1:
            # Sequential mode (original behavior)
            return self._download_sequential(ticker, all_dates, first_date)
        else:
            # Concurrent mode (new behavior)
            return self._download_concurrent(ticker, all_dates, first_date)

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
                elif response.status_code == 429:
                    # Rate limit - more aggressive backoff
                    if attempt < max_retries - 1:
                        backoff_time = initial_backoff * (3 ** attempt)  # 1s, 3s, 9s
                        tqdm.write(f"  ⚠ Rate limit hit (429). Backing off {backoff_time:.0f}s...")
                        time.sleep(backoff_time)
                    else:
                        raise Exception(f"Rate limit (429) - reduce max_workers or increase rate_limit_delay")
                else:
                    error_msg = f"API returned {response.status_code}"

                    # Don't retry on 4xx client errors (except 429 already handled)
                    if 400 <= response.status_code < 500:
                        raise Exception(error_msg)

                    # Retry on 5xx server errors
                    if attempt < max_retries - 1:
                        backoff_time = initial_backoff * (2 ** attempt)
                        tqdm.write(f"  {error_msg}. Retrying in {backoff_time}s...")
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

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        if self.rate_limit_delay <= 0:
            return

        import threading

        # Thread-safe rate limiting
        if self._request_lock is None:
            self._request_lock = threading.Lock()

        with self._request_lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time

            if time_since_last < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - time_since_last
                time.sleep(sleep_time)

            self._last_request_time = time.time()

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
            # Rate limiting
            self._rate_limit()

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
        errors = []
        rate_limit_failures = []

        pbar = tqdm(all_dates, desc=f"{ticker} options", unit="day")
        for date in pbar:
            df, error = self._download_single_date(ticker, date)

            if df is not None:
                all_data.append(df)
            elif error and "No data found (API 472)" in error:
                missing_dates += 1
                pbar.set_postfix(missing=missing_dates, refresh=False)
            elif error:
                if "Rate limit (429)" in error:
                    rate_limit_failures.append(date)
                    errors.append((date, error))
                else:
                    errors.append((date, error))
                    tqdm.write(f"[{date}] {error}")

        # Retry rate-limited dates with more conservative settings
        if rate_limit_failures:
            print(f"\n🔄 Retrying {len(rate_limit_failures)} rate-limited dates with slower settings...")
            retry_data = self._retry_failed_dates(ticker, rate_limit_failures)
            if retry_data:
                all_data.extend(retry_data)

        # Print error summary if any errors remain
        remaining_errors = [e for e in errors if e[0] not in rate_limit_failures or e[0] in [d for d, _ in errors]]
        if remaining_errors:
            print(f"\n⚠ {len(remaining_errors)} dates failed to download:")
            for date, error in remaining_errors[:5]:
                print(f"  - {date}: {error}")
            if len(remaining_errors) > 5:
                print(f"  ... and {len(remaining_errors) - 5} more")

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
        rate_limit_failures = []  # Track dates that failed due to rate limits

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
                            elif "Rate limit (429)" in error:
                                # Track rate limit failures for retry
                                rate_limit_failures.append(date)
                                errors.append((date, error))
                            else:
                                errors.append((date, error))
                                tqdm.write(f"[{date}] {error}")

                    except Exception as e:
                        errors.append((date, str(e)))
                        tqdm.write(f"[{date}] Unexpected error: {e}")

                    pbar.update(1)

        # Retry rate-limited dates with more conservative settings
        if rate_limit_failures:
            print(f"\n🔄 Retrying {len(rate_limit_failures)} rate-limited dates with slower settings...")
            retry_data = self._retry_failed_dates(ticker, rate_limit_failures)
            if retry_data:
                all_data.extend(retry_data)
                # Remove successfully retried dates from errors list
                retry_dates_set = {date for date, _ in retry_data} if retry_data else set()
                errors = [(d, e) for d, e in errors if d not in retry_dates_set]

        # Print error summary if any non-trivial errors remain
        if errors:
            print(f"\n⚠ {len(errors)} dates failed to download:")
            for date, error in errors[:5]:  # Show first 5
                print(f"  - {date}: {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")

        return self._finalize_download(all_data, ticker, start_date, missing_dates)

    def _retry_failed_dates(
        self,
        ticker: str,
        failed_dates: list
    ) -> list:
        """
        Retry failed dates with more conservative settings.

        Uses sequential mode with increased delay to avoid rate limits.

        Args:
            ticker: Stock symbol
            failed_dates: List of date strings that failed due to rate limits

        Returns:
            List of (date, dataframe) tuples for successful retries
        """
        # Store original settings
        original_delay = self.rate_limit_delay

        # Use more conservative settings for retry
        # Triple the delay and force sequential mode (already sequential in this method)
        retry_delay = max(0.3, self.rate_limit_delay * 3)
        self.rate_limit_delay = retry_delay

        print(f"  Using sequential mode with {retry_delay}s delay between requests")

        successful_retries = []
        retry_failures = 0

        for date in tqdm(failed_dates, desc=f"  Retrying {ticker}", unit="day"):
            df, error = self._download_single_date(ticker, date)

            if df is not None:
                successful_retries.append(df)
            else:
                retry_failures += 1
                if error and "Rate limit (429)" not in error:
                    tqdm.write(f"  [{date}] Still failed: {error}")

        # Restore original settings
        self.rate_limit_delay = original_delay

        if successful_retries:
            print(f"  ✓ Successfully retried {len(successful_retries)}/{len(failed_dates)} dates")
        if retry_failures:
            print(f"  ✗ {retry_failures} dates still failed after retry")

        return successful_retries

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
