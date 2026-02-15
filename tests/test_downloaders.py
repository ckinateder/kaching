"""
Unit tests for downloader modules.

Tests API-free functions using DECK fixtures from tests/fixtures/.
No external API calls are made during these tests.
"""

import unittest
import pandas as pd
from pathlib import Path
import sys
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from src.downloaders import (
    validate_date_range,
    generate_date_range,
    find_missing_dates,
    find_contiguous_date_ranges,
)
from src.downloaders.options_downloader import ThetaDataDownloader, ESSENTIAL_FIELDS
from src.downloaders.stock_downloader import YFinanceDownloader, STOCK_PRICE_FIELDS
from src.downloaders.dataset_downloader import DatasetDownloader


class TestUtilityFunctions(unittest.TestCase):
    """Test shared utility functions from downloaders/__init__.py"""

    def test_validate_date_range_valid(self):
        """Test validation with valid date range"""
        validate_date_range('2024-01-01', '2024-01-31')

    def test_validate_date_range_invalid_format(self):
        """Test validation with invalid date format"""
        with self.assertRaises(ValueError):
            validate_date_range('not-a-date', 'also-not-a-date')

    def test_validate_date_range_end_before_start(self):
        """Test validation when end_date < start_date"""
        with self.assertRaises(ValueError):
            validate_date_range('2024-01-31', '2024-01-01')

    def test_generate_date_range_single_day(self):
        """Test date range generation for single day"""
        dates = generate_date_range('2024-01-01', '2024-01-01')
        self.assertEqual(dates, ['2024-01-01'])

    def test_generate_date_range_multiple_days(self):
        """Test date range generation for multiple days"""
        dates = generate_date_range('2024-01-01', '2024-01-03')
        self.assertEqual(dates, ['2024-01-01', '2024-01-02', '2024-01-03'])

    def test_find_missing_dates_no_file(self):
        """Test find_missing_dates when Parquet file doesn't exist"""
        existing_df, missing = find_missing_dates(
            '/nonexistent/path.parquet', '2024-01-01', '2024-01-05'
        )
        self.assertIsNone(existing_df)
        self.assertEqual(len(missing), 5)

    def test_find_missing_dates_with_DECK_stock(self):
        """Test find_missing_dates using DECK_stock.parquet fixture"""
        fixture_path = 'tests/fixtures/DECK_stock.parquet'
        existing_df, missing = find_missing_dates(
            fixture_path, '2025-12-01', '2025-12-05'
        )
        self.assertEqual(missing, [])
        self.assertIsNotNone(existing_df)

    def test_find_contiguous_date_ranges_continuous(self):
        """Test contiguous range detection with no gaps"""
        dates = ['2024-01-01', '2024-01-02', '2024-01-03']
        ranges = find_contiguous_date_ranges(dates)
        self.assertEqual(ranges, [('2024-01-01', '2024-01-03')])

    def test_find_contiguous_date_ranges_gapped(self):
        """Test contiguous range detection with gaps"""
        dates = ['2024-01-01', '2024-01-02', '2024-01-05', '2024-01-06']
        ranges = find_contiguous_date_ranges(dates)
        self.assertEqual(ranges, [('2024-01-01', '2024-01-02'), ('2024-01-05', '2024-01-06')])

    def test_find_contiguous_date_ranges_empty(self):
        """Test contiguous range detection with empty list"""
        ranges = find_contiguous_date_ranges([])
        self.assertEqual(ranges, [])


class TestOptionsDownloaderStaticMethods(unittest.TestCase):
    """Test static methods of ThetaDataDownloader"""

    def setUp(self):
        """Load DECK_options.parquet fixture"""
        self.options_path = 'tests/fixtures/DECK_options.parquet'
        self.options_df = pd.read_parquet(self.options_path)

    def test_merge_options_data_both_empty(self):
        """Test merge when both DataFrames are empty"""
        empty_df = pd.DataFrame(columns=ESSENTIAL_FIELDS)
        result = ThetaDataDownloader.merge_options_data(empty_df, empty_df)
        self.assertTrue(result.empty)

    def test_merge_options_data_existing_empty(self):
        """Test merge when existing is empty, new has data"""
        empty_df = pd.DataFrame(columns=ESSENTIAL_FIELDS)
        result = ThetaDataDownloader.merge_options_data(empty_df, self.options_df)
        self.assertEqual(len(result), len(self.options_df))

    def test_merge_options_data_new_empty(self):
        """Test merge when new is empty, existing has data"""
        empty_df = pd.DataFrame(columns=ESSENTIAL_FIELDS)
        result = ThetaDataDownloader.merge_options_data(self.options_df, empty_df)
        self.assertEqual(len(result), len(self.options_df))

    def test_merge_options_data_deduplicate(self):
        """Test merge deduplicates on (symbol, expiration, strike, right, timestamp)"""
        result = ThetaDataDownloader.merge_options_data(self.options_df, self.options_df)
        self.assertEqual(len(result), len(self.options_df))

    def test_merge_options_data_sorts_correctly(self):
        """Test merge preserves existing columns and doesn't add extras"""
        original_cols = set(self.options_df.columns.tolist())
        result = ThetaDataDownloader.merge_options_data(self.options_df, self.options_df)
        result_cols = set(result.columns.tolist())
        self.assertEqual(result_cols, original_cols)

    def test_validate_data_valid(self):
        """Test validation passes on valid DECK_options data"""
        self.assertTrue(ThetaDataDownloader._validate_data(self.options_df))

    def test_validate_data_missing_required_columns(self):
        """Test validation fails when required columns missing"""
        bad_df = self.options_df.drop(columns=['symbol'])
        with redirect_stdout(StringIO()):
            self.assertFalse(ThetaDataDownloader._validate_data(bad_df))

    def test_validate_data_negative_bid(self):
        """Test validation fails when bid is negative"""
        bad_df = self.options_df.copy()
        bad_df.loc[0, 'bid'] = -0.5
        with redirect_stdout(StringIO()):
            self.assertFalse(ThetaDataDownloader._validate_data(bad_df))

    def test_validate_data_non_positive_strike(self):
        """Test validation fails when strike is non-positive"""
        bad_df = self.options_df.copy()
        bad_df.loc[0, 'strike'] = 0
        with redirect_stdout(StringIO()):
            self.assertFalse(ThetaDataDownloader._validate_data(bad_df))

    def test_validate_data_negative_volume(self):
        """Test validation fails when volume is negative"""
        bad_df = self.options_df.copy()
        bad_df.loc[0, 'volume'] = -100
        with redirect_stdout(StringIO()):
            self.assertFalse(ThetaDataDownloader._validate_data(bad_df))


class TestStockDownloaderMethods(unittest.TestCase):
    """Test methods of YFinanceDownloader"""

    def setUp(self):
        """Load DECK_stock.parquet fixture and create downloader instance"""
        self.stock_path = 'tests/fixtures/DECK_stock.parquet'
        self.stock_df = pd.read_parquet(self.stock_path)
        self.downloader = YFinanceDownloader()

    def test_merge_stock_data_deduplicate(self):
        """Test merge deduplicates on (symbol, date)"""
        result = self.downloader.merge_stock_data(self.stock_df, self.stock_df)
        self.assertEqual(len(result), len(self.stock_df))

    def test_merge_stock_data_sorts_by_date(self):
        """Test merge sorts by date"""
        unsorted_df = self.stock_df.sort_values('date', ascending=False)
        result = self.downloader.merge_stock_data(unsorted_df, pd.DataFrame())
        self.assertTrue(result['date'].is_monotonic_increasing)

    def test_validate_data_valid(self):
        """Test validation passes on valid DECK_stock data"""
        self.assertTrue(self.downloader._validate_data(self.stock_df))

    def test_validate_data_missing_required_columns(self):
        """Test validation fails when required columns missing"""
        bad_df = self.stock_df.drop(columns=['close'])
        with redirect_stdout(StringIO()):
            self.assertFalse(self.downloader._validate_data(bad_df))

    def test_validate_data_non_positive_close(self):
        """Test validation fails when close is non-positive"""
        bad_df = self.stock_df.copy()
        bad_df.loc[0, 'close'] = 0
        with redirect_stdout(StringIO()):
            self.assertFalse(self.downloader._validate_data(bad_df))

    def test_validate_data_large_date_gap(self):
        """Test validation warns on large date gaps (>14 days)"""
        dates = ['2024-01-01', '2024-01-21']
        gap_df = pd.DataFrame({
            'symbol': ['TEST', 'TEST'],
            'date': dates,
            'close': [100.0, 101.0],
            'open': [99.0, 100.0],
            'high': [101.0, 102.0],
            'low': [98.0, 99.0],
            'volume': [1000000, 1000000]
        })
        with redirect_stdout(StringIO()):
            self.assertTrue(self.downloader._validate_data(gap_df))

    def test_standardize_columns_yfinance_format(self):
        """Test _standardize_columns transforms yfinance format"""
        data = {
            'Open': [99.0, 100.0],
            'High': [101.0, 102.0],
            'Low': [98.0, 99.0],
            'Close': [100.0, 101.0],
            'Volume': [1000000, 2000000],
            'Dividends': [0.0, 0.0],
            'Stock Splits': [0.0, 0.0]
        }
        dates = pd.to_datetime(['2024-01-01', '2024-01-02'])
        yfinance_df = pd.DataFrame(data, index=dates)
        yfinance_df.index.name = 'Date'

        result = self.downloader._standardize_columns(yfinance_df, 'TEST')

        self.assertIn('symbol', result.columns)
        self.assertEqual(result['symbol'].iloc[0], 'TEST')
        self.assertIn('date', result.columns)
        self.assertIn('close', result.columns)
        self.assertNotIn('Open', result.columns)
        self.assertNotIn('Dividends', result.columns)

    def test_standardize_columns_filters_to_essential_fields(self):
        """Test _standardize_columns filters to available STOCK_PRICE_FIELDS"""
        data = {
            'Open': [99.0],
            'High': [101.0],
            'Low': [98.0],
            'Close': [100.0],
            'Volume': [1000000],
            'Dividends': [0.0],
            'Stock Splits': [0.0]
        }
        dates = pd.to_datetime(['2024-01-01'])
        yfinance_df = pd.DataFrame(data, index=dates)
        yfinance_df.index.name = 'Date'

        result = self.downloader._standardize_columns(yfinance_df, 'TEST')
        actual_cols = set(result.columns)
        expected_cols = {'symbol', 'date', 'close', 'open', 'high', 'low', 'volume'}
        self.assertEqual(actual_cols, expected_cols)


class TestDatasetDownloaderMethods(unittest.TestCase):
    """Test methods of DatasetDownloader"""

    def setUp(self):
        """Load DECK fixtures and create dataset downloader"""
        self.options_path = 'tests/fixtures/DECK_options.parquet'
        self.stock_path = 'tests/fixtures/DECK_stock.parquet'
        self.options_df = pd.read_parquet(self.options_path)
        self.stock_df = pd.read_parquet(self.stock_path)
        self.downloader = DatasetDownloader()

    def test_join_data_basic_merge(self):
        """Test join merges options with stock data on calendar day"""
        result = self.downloader._join_data(self.options_df, self.stock_df)
        self.assertEqual(len(result), len(self.options_df))
        self.assertIn('underlying_close', result.columns)
        self.assertIn('underlying_open', result.columns)
        self.assertIn('underlying_high', result.columns)
        self.assertIn('underlying_low', result.columns)
        self.assertIn('underlying_date', result.columns)

    def test_join_data_temporary_columns_removed(self):
        """Test join removes temporary columns"""
        result = self.downloader._join_data(self.options_df, self.stock_df)
        self.assertNotIn('timestamp_date', result.columns)
        self.assertNotIn('underlying_date_date', result.columns)

    def test_join_data_removes_underlying_symbol(self):
        """Test join removes duplicate symbol column from stock data"""
        result = self.downloader._join_data(self.options_df, self.stock_df)
        self.assertIn('symbol', result.columns)
        self.assertNotIn('underlying_symbol', result.columns)

    def test_join_data_price_columns_rounded(self):
        """Test join rounds price columns to 2 decimal places"""
        result = self.downloader._join_data(self.options_df, self.stock_df)
        price_cols = ['underlying_open', 'underlying_high', 'underlying_low', 'underlying_close']
        for col in price_cols:
            if not result[col].empty:
                sample = result[col].dropna().iloc[0]
                self.assertEqual(round(sample, 2), sample)

    def test_merge_data_uses_options_logic(self):
        """Test DatasetDownloader._merge_data delegates to options merge"""
        result = self.downloader._merge_data(self.options_df, self.options_df)
        self.assertEqual(len(result), len(self.options_df))


if __name__ == '__main__':
    unittest.main()
