# Plan: KaChing Walk-Forward Backtester Notebook

## Context
Currently `macro_summary.py` scores tickers by historical P&L distributions but never simulates actual trades. This plan adds a full walk-forward backtester as a Jupyter notebook that simulates both legs of the KaChing strategy (weekly short puts + protective long put), tests multiple OTM bucket selection criteria, and compares Thu vs Fri entries across all A-tier tickers.

---

## Output
`notebooks/kaching_backtest.ipynb` — self-contained, runs top-to-bottom

---

## Critical Constraints
- **Use `data/raw/dataset/` NOT `data/processed/`** — processed files already have `close_at_expiry`, causing a merge collision inside `filter_weekly_put_options()`
- Reuse `filter_weekly_put_options`, `OTM_LABELS`, `OTM_BINS`, `MONEYNESS_THRESHOLD` from `src/postprocess/__init__.py`
- No new source files in `src/` — all logic inline in the notebook

---

## Strategy Being Simulated

### Short leg (weekly, repeated each test window)
- Entry: Thu or Fri, sell a put in the best OTM bucket, 6-9 DTE
- P&L: `bid - max(0, strike - close_at_expiry)` (already in data as `pnl` column)
- One trade per week (preference: highest bid when multiple strikes in bucket)

### Long leg (protective put, once per 120-day cycle)
- Entry: buy a put with DTE 90-150, delta ~-0.25 (5-7% OTM)
- Entry cost: `ask` price on first available day of test window
- Terminal value: `max(0, strike - close_at_expiry)` at expiry
- Long P&L: `terminal_value - ask_paid`

---

## Walk-Forward Parameters (defaults)
| Parameter | Value | Rationale |
|---|---|---|
| `TRAIN_DAYS` | 180 | ~6 months, enough market cycles |
| `TEST_DAYS` | 120 | = 1 full protective put cycle, ~16 weekly trades |
| `STEP_DAYS` | 60 | Half a cycle, ~27 windows on 4yr dataset |

---

## OTM Bucket Selection (4 criteria shown, 1 used)
Training data determines which bucket to sell in the test window:
- `"ev"` — max avg P&L
- `"winrate"` — max win rate
- `"sharpe"` — max (mean P&L / std P&L)
- `"composite"` — 0.5×norm(EV) + 0.3×win_rate + 0.2×norm(Sharpe) ← default

---

## Notebook Cell Structure (~620 lines, 20 cells)

### Section 1: Setup (cells 1-3)
- **Cell 1**: Imports (`pandas`, `numpy`, `matplotlib`, `seaborn`, `tqdm`); add project root to `sys.path`; import `filter_weekly_put_options`, `OTM_LABELS`, `OTM_BINS`, `MONEYNESS_THRESHOLD` from `src.postprocess`
- **Cell 2**: Global config — all params in one place (`TRAIN_DAYS`, `TEST_DAYS`, `STEP_DAYS`, `TIER_FILTER="A"`, `LONG_DTE_MIN/MAX`, `LONG_DELTA_TGT=-0.25`, `LONG_DELTA_TOL=0.05`, `SELECTION_METHOD="composite"`, `ENTRY_DOW=None`)
- **Cell 3**: Load `outputs/kaching_scored_stocks.csv`, strip `$`/`%` formatting from string columns, filter to A-tier universe

### Section 2: Helper Functions (cells 4-5)
- **Cell 4**: Short put helpers
  - `pick_trade(day_df)` — returns row with highest `bid`; returns `None` if empty
  - `select_bucket_training(train_df, method)` — groups by `otm_bucket`, computes EV/winrate/Sharpe/composite, requires `n >= 5` per bucket, returns best label or `None`
  - `get_trade_for_week(week_df, target_bucket)` — cascades to adjacent buckets if target empty; returns `(trade_row, actual_bucket_used)`

- **Cell 5**: Long put helpers
  - `filter_long_puts(raw_df, dte_min, dte_max, delta_target, delta_tol)` — filters to PUT, DTE range, delta range (widens ±0.05 up to ±0.15 if no match), applies split ratio filter, returns one row per calendar date (last quote of day)
  - `price_long_put_at_expiry(long_put_row, raw_df)` — looks up `underlying_close` on `expiration` date, returns `max(0, strike - close)`

### Section 3: Walk-Forward Engine (cells 6-8)
- **Cell 6**: `run_walkforward_single(ticker, entry_dow, selection_method)` — core function
  - Loads `data/raw/dataset/{ticker}.parquet`
  - Calls `filter_weekly_put_options(raw_df)` for short puts
  - Calls `filter_long_puts(raw_df)` for long puts
  - Applies DOW filter if `entry_dow` is set
  - Loops through windows: compute `train_df`, `test_df`, select bucket (all 4 methods stored), simulate week-by-week trades, enter long put at window start
  - Returns `{"ticker", "trades": DataFrame, "long_puts": DataFrame, "windows": DataFrame}`

  **Important**: pass `raw_df` as-is to both filter functions — `filter_weekly_put_options` rebinds locally, won't clobber the caller's reference

- **Cell 7**: Multi-ticker runner — `tqdm` loop over `universe`, calls `run_walkforward_single`, catches exceptions, stores in `results` dict

- **Cell 8**: Aggregate — `pd.concat` all `trades`, `long_puts`, `windows` DataFrames across tickers. Deduplicate trades by `(ticker, quote_date, strike, expiration)` to avoid double-counting (walk-forward windows overlap by design). Add `total_pnl = short_pnl_total + long_pnl` per window.

### Section 4: Metrics (cells 9-10)
- **Cell 9**: `compute_sharpe(pnl_series)` — annualized (`× sqrt(52)`); `compute_max_drawdown(cumulative)` — peak-to-trough; per-ticker table with `n_trades, total_short_pnl, total_long_pnl, net_pnl, win_rate, avg_weekly_premium, sharpe, max_drawdown, fallback_rate`

- **Cell 10**: Thu vs Fri entry comparison — re-runs first 5 tickers with `entry_dow=3` and `entry_dow=4` separately; pivot table comparing `total_pnl`, `win_rate`, `sharpe`

### Section 5: Visualizations (cells 11-18)
- **Cell 11**: Equity curves — grid of subplots (N×3), one per ticker, short leg cumulative P&L vs time
- **Cell 12**: Short vs long breakdown — best-Sharpe ticker, dual panel: top=equity curve, bottom=per-window bar chart (short P&L stacked against long P&L)
- **Cell 13**: Drawdown curves — top 8 tickers on same axes
- **Cell 14**: Win rate over windows — line plot, one series per ticker (top 6), 50% reference line
- **Cell 15**: Bucket stability heatmap — `imshow` of chosen bucket per (ticker, window), colorbar = `OTM_LABELS`
- **Cell 16**: P&L box plots by OTM bucket — side-by-side: all A-tier tickers combined vs best single ticker; `showfliers=False`
- **Cell 17**: Sharpe ranking bar chart — horizontal, coral=negative, steelblue=positive
- **Cell 18**: Net P&L ranking bar chart — horizontal, short+long combined

### Section 6: Summary (cells 19-20)
- **Cell 19**: Printed summary block — universe, walk-forward params, total trades, overall win rate, avg weekly premium, total short/long/net P&L, top 5 by Sharpe
- **Cell 20**: Data quality report — fallback rate per ticker, missing long put data warnings

---

## Key Edge Cases Handled
| Case | Handling |
|---|---|
| OTM bucket empty for a week | Cascade to adjacent bucket (outward first); log `fallback_used=True` |
| Multiple strikes in same bucket+week | Pick highest `bid` |
| Long put — no delta match | Widen tolerance by 0.05 up to ±0.15 total |
| Long put expiry price missing | Return `NaN`; window `long_pnl` = NaN (excluded from net P&L sum) |
| All buckets fail `n >= 5` in training | Return `None` bucket; skip window |
| Overlapping walk-forward windows | Deduplicate by `(ticker, quote_date, strike, expiration)` before equity curve |

---

## Files to Create/Modify
| File | Action |
|---|---|
| `notebooks/kaching_backtest.ipynb` | **Create** (~620 lines, 20 cells) |

## Files Referenced (read-only)
| File | Purpose |
|---|---|
| `src/postprocess/__init__.py` | Import `filter_weekly_put_options`, `OTM_LABELS`, `OTM_BINS`, `MONEYNESS_THRESHOLD` |
| `data/raw/dataset/{ticker}.parquet` | Raw options+stock data per ticker |
| `outputs/kaching_scored_stocks.csv` | A-tier ticker universe (has `$`/`%` string formatting to strip) |
| `scripts/main.py` | Reference for existing plot style |

---

## Verification Steps
1. Run Cell 1-3 — universe loads cleanly, shows ~30 A-tier tickers
2. Run Cell 5 standalone on AAPL — `filter_long_puts()` returns non-empty df with delta ~-0.25
3. Run Cell 6 on single ticker (SNAP or MARA) — verify window count ≈ 27, trades per window ≈ 10-16
4. Check `all_trades_df` has no duplicate `(ticker, quote_date, strike, expiration)` rows
5. Confirm `long_puts_df` has rows for most tickers (warning if any are empty)
6. Spot-check P&L math: a winning trade should have `bid > max(0, strike - close_at_expiry)` ✓
7. Run full notebook top-to-bottom — all cells execute without errors in ~2-3 min
