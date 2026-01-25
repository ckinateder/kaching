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


# Essential fields to keep (drop unnecessary columns to minimize data redundancy)
ESSENTIAL_FIELDS = [
    # Contract identification
    'symbol',
    'expiration',
    'strike',
    'right',

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
        end_date: str,
        output_dir: str = 'data/raw',
        check_existing: bool = True
    ) -> pd.DataFrame:
        """
        Download EOD options data with Greeks for all expirations.

        Downloads data day-by-day (API constraint for expiration=*) with progress logging.
        Supports incremental downloads by checking existing CSV files.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)
            output_dir: Directory to check for existing CSV (for incremental download)
            check_existing: If True, check existing CSV and only download missing dates

        Returns:
            pd.DataFrame with options data for all dates in range

        Raises:
            ValueError: If date format is invalid or end_date < start_date
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

        # Generate full date range
        all_dates = self._generate_date_range(start_date, end_date)

        # Check for existing data and identify missing dates
        existing_df = None
        missing_dates = all_dates

        if check_existing:
            existing_df, missing_dates = self._check_existing_data(
                ticker, start_date, end_date, output_dir
            )

            if not missing_dates:
                print(f"✓ All data already exists for {ticker} ({start_date} to {end_date})")
                return existing_df

            print(f"Found existing data. Need to download {len(missing_dates)} missing dates.")

        # Download data day by day
        all_data = []
        total_days = len(missing_dates)
        total_contracts = 0

        print(f"\nDownloading {ticker} options data for {total_days} days...")

        for i, date in enumerate(missing_dates, 1):
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

        # If we have existing data, merge it
        if existing_df is not None and not existing_df.empty:
            print(f"\nMerging with existing data ({len(existing_df):,} existing contracts)...")
            result_df = pd.concat([existing_df, result_df], ignore_index=True)

            # Sort by timestamp, expiration, strike and remove any duplicates
            result_df = result_df.sort_values(['timestamp', 'expiration', 'strike', 'right'])
            result_df = result_df.drop_duplicates(
                subset=['symbol', 'expiration', 'strike', 'right', 'timestamp'],
                keep='last'
            )

        print(f"\n✓ Download complete!")
        print(f"  Total contracts: {len(result_df):,}")
        print(f"  Date range: {result_df['timestamp'].min()} to {result_df['timestamp'].max()}")
        print(f"  Unique expirations: {result_df['expiration'].nunique()}")

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
        csv_path = Path(output_dir) / f"{ticker}_options_eod.csv"

        # Generate requested date range
        requested_dates = self._generate_date_range(start_date, end_date)

        # If CSV doesn't exist, all dates are missing
        if not csv_path.exists():
            return None, requested_dates

        try:
            # Load existing CSV
            df = pd.read_csv(csv_path)

            if df.empty:
                return None, requested_dates

            # Parse timestamp column to datetime and extract unique dates
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            existing_dates = df['timestamp'].dt.date.unique()
            existing_dates_str = [d.strftime('%Y-%m-%d') for d in existing_dates]

            # Find missing dates
            missing_dates = [d for d in requested_dates if d not in existing_dates_str]

            return df, missing_dates

        except Exception as e:
            print(f"⚠ Warning: Could not read existing CSV: {e}")
            print(f"  Proceeding as if no existing data...")
            return None, requested_dates

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
