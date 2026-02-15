"""
Base downloader class providing unified download interface.

This module defines the abstract base class that all downloaders inherit from,
providing a consistent API and eliminating duplicate orchestration logic.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import pandas as pd

# Import will be done at runtime to avoid circular dependency
# download_and_save_with_incremental is in downloaders/__init__.py


class BaseDownloader(ABC):
    """
    Abstract base class for all data downloaders.

    Provides a unified download() method that handles both download-only and
    download-and-save operations, with support for incremental downloads.

    Subclasses must implement template methods for data-source-specific logic.
    """

    def __init__(self, max_workers: int = 8):
        """
        Initialize base downloader.

        Args:
            max_workers: Maximum concurrent workers for parallel downloads.
                        Set to 1 for sequential mode. Default: 8
        """
        self.max_workers = max_workers

    def download(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        save: bool = False,
        filepath: Optional[str] = None,
        incremental: bool = True
    ) -> pd.DataFrame:
        """
        Unified download method for all downloaders.

        This method provides two operating modes:
        1. Download-only (save=False): Returns DataFrame without saving to disk
        2. Download-and-save (save=True): Downloads, saves to Parquet, returns DataFrame

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format (inclusive)
            save: If True, saves data to filepath. If False, returns DataFrame only.
            filepath: Path to save Parquet file. Required when save=True.
            incremental: If True and save=True, checks existing Parquet file and only downloads
                        missing dates. If False, re-downloads entire range.

        Returns:
            pd.DataFrame: Downloaded data with standardized columns

        Raises:
            ValueError: If save=True but filepath is None
            RequestException: If API request fails after retries
            ValueError: If downloaded data fails validation

        Examples:
            # Download-only mode (no save)
            downloader = ThetaDataDownloader()
            df = downloader.download('AAPL', '2024-01-01', '2024-01-31')

            # Download-and-save mode with incremental
            df = downloader.download(
                'AAPL', '2024-01-01', '2024-01-31',
                save=True,
                filepath='data/raw/AAPL_options.parquet',
                incremental=True
            )

            # Download-and-save mode without incremental (full re-download)
            df = downloader.download(
                'AAPL', '2024-01-01', '2024-01-31',
                save=True,
                filepath='data/raw/AAPL_options.parquet',
                incremental=False
            )
        """
        # Validate parameters
        if save and filepath is None:
            raise ValueError(
                "filepath must be provided when save=True. "
                "Either provide filepath or set save=False."
            )
        
        try:
            # Route to appropriate handler
            if not save:
                # Download-only mode
                return self._download_only(ticker, start_date, end_date)
            else:
                # Download-and-save mode
                return self._download_and_save(
                    ticker, start_date, end_date, filepath, incremental
                )
        except KeyError as e:
            print("Interrupt")

    def _download_and_save(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        filepath: str,
        incremental: bool
    ) -> pd.DataFrame:
        """
        Internal method that delegates to existing incremental download helper.

        This method bridges the unified API to the existing download_and_save_with_incremental
        helper function that handles incremental logic, Parquet I/O, and logging.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            filepath: Path to save Parquet file
            incremental: If True, only download missing dates

        Returns:
            pd.DataFrame: Complete dataset (existing + new data if incremental)
        """
        # Import here to avoid circular dependency
        from . import download_and_save_with_incremental

        return download_and_save_with_incremental(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            filepath=filepath,
            incremental=incremental,
            download_func=self._download_only,
            merge_func=self._merge_data,
            date_column=self._get_date_column(),
            parse_timestamp=self._parse_timestamp(),
            data_type_name=self._get_data_type_name(),
            essential_fields=self._get_essential_fields()
        )

    # Abstract methods that subclasses must implement

    @abstractmethod
    def _download_only(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Pure download logic without any saving.

        This method contains the core data-fetching logic specific to each
        data source (Theta Data API, yfinance, etc.). It should handle:
        - Making API requests
        - Parsing responses
        - Basic data validation
        - Returning standardized DataFrame

        Args:
            ticker: Stock ticker symbol
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format

        Returns:
            pd.DataFrame: Raw downloaded data with essential fields

        Raises:
            RequestException: If API request fails
            ValueError: If data validation fails
        """
        pass

    @abstractmethod
    def _merge_data(
        self,
        existing_df: pd.DataFrame,
        new_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Merge existing and newly downloaded data, removing duplicates.

        Different data sources have different deduplication logic:
        - Options: Deduplicate on (symbol, timestamp, strike, expiration, right)
        - Stocks: Deduplicate on (symbol, date)
        - Datasets: Use options logic (most granular)

        Args:
            existing_df: Previously downloaded data from Parquet file
            new_df: Newly downloaded data from API

        Returns:
            pd.DataFrame: Merged data with duplicates removed
        """
        pass

    @abstractmethod
    def _get_date_column(self) -> str:
        """
        Return the name of the date/timestamp column for this data source.

        Returns:
            str: Column name ('timestamp' for options, 'date' for stocks)
        """
        pass

    @abstractmethod
    def _parse_timestamp(self) -> bool:
        """
        Whether to parse the date column as timestamp or date-only.

        Returns:
            bool: True if column should be parsed as datetime with time component,
                 False if date-only
        """
        pass

    @abstractmethod
    def _get_data_type_name(self) -> str:
        """
        Return human-readable name for this data type (for logging).

        Returns:
            str: Data type name ('contracts' for options, 'trading days' for stocks)
        """
        pass

    @abstractmethod
    def _get_essential_fields(self) -> list:
        """
        Return list of essential column names for this data source.

        These fields are used for:
        - Filtering downloaded data to minimal required columns
        - Validating that required fields are present

        Returns:
            list: Column names (e.g., ESSENTIAL_FIELDS for options)
        """
        pass
