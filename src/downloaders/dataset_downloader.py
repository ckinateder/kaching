"""
Combined downloader for both options and stock price data.

This module provides a DatasetDownloader class that downloads both options data
and stock prices for building a complete dataset over a specified date range.
"""

from typing import Optional
import pandas as pd

from .base_downloader import BaseDownloader
from .options_downloader import ThetaDataDownloader
from .stock_downloader import YFinanceDownloader
from . import validate_date_range


class DatasetDownloader(BaseDownloader):
    """
    Download combined options and stock price data.

    This downloader coordinates both ThetaDataDownloader and YFinanceDownloader
    to produce a single joined dataset with options data and corresponding
    stock prices.
    """

    def __init__(
        self,
        options_base_url: str = 'http://127.0.0.1:25503/v3',
        max_workers: int = 8,
        rate_limit_delay: float = 0.1
    ):
        """
        Initialize the dataset downloader.

        Args:
            options_base_url: Base URL for Theta Data API (default: localhost terminal)
            max_workers: Maximum concurrent workers for options downloads (default: 8)
            rate_limit_delay: Minimum delay between API requests in seconds (default: 0.1)
        """
        super().__init__(max_workers=max_workers)
        self.options_downloader = ThetaDataDownloader(
            base_url=options_base_url,
            max_workers=max_workers,
            rate_limit_delay=rate_limit_delay
        )
        self.stock_downloader = YFinanceDownloader(max_workers=max_workers)

    def _download_only(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        dates_to_download: Optional[list] = None
    ) -> pd.DataFrame:
        """
        Download both options data and stock prices, then join them.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)
            dates_to_download: Optional list of specific dates to download. If provided,
                             only these dates will be downloaded for options data.

        Returns:
            Combined DataFrame with options data and stock prices

        Raises:
            ValueError: If date format is invalid, end_date < start_date, or invalid ticker
            Exception: If API requests fail after all retries
        """
        # Validate date inputs
        validate_date_range(start_date, end_date)

        # Download options data (quiet mode - downloaders handle their own logging)
        # CRITICAL: Call _download_only directly to pass dates_to_download parameter
        # This ensures we download only the specific missing dates, not the entire merged range
        options_df = self.options_downloader._download_only(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            dates_to_download=dates_to_download
        )

        # Download stock prices
        # CRITICAL: Must pass save=False explicitly to avoid triggering stock_downloader's own incremental logic
        stock_df = self.stock_downloader.download(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            save=False  # Explicitly set to False to ensure we get _download_only, not incremental logic
        )

        # Combine the data
        combined_df = self._join_data(options_df, stock_df)

        # Only show summary if we got data
        if not combined_df.empty:
            print(f"\n✓ Dataset combined: {len(combined_df):,} records, {combined_df['expiration'].nunique()} expirations")

        return combined_df

    def _join_data(
        self,
        options_df: pd.DataFrame,
        stock_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Join options data with stock price data.

        Args:
            options_df: Options DataFrame with timestamp column
            stock_df: Stock DataFrame with date column

        Returns:
            Combined DataFrame with options and stock data
        """
        # Convert to datetime for proper joining
        options_df['timestamp'] = pd.to_datetime(options_df['timestamp'])
        options_df['expiration'] = pd.to_datetime(options_df['expiration'])
        stock_df['date'] = pd.to_datetime(stock_df['date'])

        # Add "underlying_" prefix to stock_df columns
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

        return combined_df

    def _download_and_save(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        filepath: str,
        incremental: bool
    ) -> pd.DataFrame:
        """
        Override base class to save options, stock, and dataset each to their own folder.

        Expected filepath: data/raw/dataset/<TICKER>.parquet
        Sibling folders:   data/raw/option/<TICKER>.parquet
                           data/raw/stock/<TICKER>.parquet
        """
        from pathlib import Path
        from . import create_output_directory

        filepath = Path(filepath)
        base_dir = filepath.parent.parent  # data/raw/

        options_path = base_dir / 'option' / filepath.name
        stock_path   = base_dir / 'stock'  / filepath.name

        # Sub-downloaders handle their own incremental logic
        options_df = self.options_downloader.download(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            save=True,
            filepath=str(options_path),
            incremental=incremental
        )
        stock_df = self.stock_downloader.download(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            save=True,
            filepath=str(stock_path),
            incremental=incremental
        )

        combined_df = self._join_data(options_df, stock_df)

        create_output_directory(str(filepath))
        combined_df.to_parquet(str(filepath), index=False)
        print(f"✓ Saved {len(combined_df):,} combined records to {filepath}")

        return combined_df

    # Abstract method implementations

    def _merge_data(
        self,
        existing_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge combined datasets using options merge logic.

        Since the combined data contains options data, we use the same
        deduplication logic as options (most granular).
        """
        # Use options merge logic since we have options data
        return ThetaDataDownloader.merge_options_data(existing_df, new_df)

    def _get_date_column(self) -> str:
        """Return date column name (timestamp from options data)."""
        return 'timestamp'

    def _parse_timestamp(self) -> bool:
        """Dataset has timestamp with time component."""
        return True

    def _get_data_type_name(self) -> str:
        """Return human-readable data type name."""
        return 'combined records'

    def _get_essential_fields(self) -> list:
        """
        Return essential fields for combined dataset.

        This includes all options fields plus stock price fields.
        """
        from .options_downloader import ESSENTIAL_FIELDS
        from .stock_downloader import STOCK_PRICE_FIELDS

        # Combine both field lists, adding underlying_ prefix to stock fields
        stock_fields_prefixed = [f'underlying_{f}' for f in STOCK_PRICE_FIELDS if f != 'symbol']
        return ESSENTIAL_FIELDS + stock_fields_prefixed


if __name__ == "__main__":
    # Example usage
    downloader = DatasetDownloader()

    tickers = ["TTD", "DECK"]
    for ticker in tickers:
        df = downloader.download(
            ticker=ticker,
            start_date='2025-12-01',
            end_date='2025-12-31',
        )
