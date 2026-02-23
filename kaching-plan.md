# KaChing Options Pricing Tool - Implementation Plan

## Overview

Build a semi-automated options pricing tool that helps select optimal strike prices for the "Weekly Cash KaChing" put spread strategy. The tool uses **empirical P&L distributions** from historical options data rather than predictive modeling.

### Core Philosophy
- **Not predicting:** "Will SCHW go up?"
- **Actually answering:** "When selling 1.5% OTM puts, what was the actual P&L distribution?"
- Human selects stocks, tool optimizes pricing based on historical outcomes

### Two Operating Modes

**Mode 1: Full Setup (Initial Position)**
- Use case: Starting a new position on a stock
- Recommends both long put AND weekly short put
- Frequency: Once per ~120 days per stock

**Mode 2: Weekly Selection (Primary Use Case)**
- Use case: You already have a protective long put
- Just recommends weekly short put above your existing floor
- Frequency: Every Thursday/Friday for active positions (16+ times per cycle)
- **This is what you'll use 95% of the time**

The tool is optimized for Mode 2 - quick Thursday morning analysis of multiple active positions.

---

## Phase 1: Data Foundation (Weeks 1-2)

### 1.1 Historical Data Preparation

**Input Data Requirements:**
- 1 year of end-of-day options data (all optionable US stocks/ETFs/indices)
- Includes: bid, ask, Greeks (delta, theta, vega, IV), volume, open interest
- Stock price data (daily close) for the same period

**Data Source:**
- Theta Data API
- https://docs.thetadata.io/api-reference/option/option-history-eod

### 1.1a Data Transformation

**Core Transformations:**

0. **Stock split price alignment filter** *(discovered in implementation)*
   - Theta Data's `underlying_price` and yfinance's `underlying_close` are on different scales
     when a stock has had a split — yfinance backward-adjusts all historical prices, Theta does not
   - This causes P&L calculations to be wildly wrong for pre-split data (strikes in pre-split dollars,
     expiry price in post-split dollars → fictional losses of hundreds of dollars per share)
   - Fix: filter rows where `underlying_price / underlying_close` is outside 0.9–1.1
   - This automatically excludes the corrupted historical window for any ticker that has split;
     the cutoff date is ticker-specific and requires no manual configuration
   - Side effect: effective history is shorter for split tickers (e.g. GOOG data only usable from Jul 2022,
     DECK from Sep 2024)

1. **Filter to weekly options only**
   - DTE 6–9 days (targets next-week expiry; 7 = Friday entry, 8 = Thursday entry, ±1 for edge cases)
   - This is the largest single row reduction (~90% of Thu/Fri rows) because each day has ~20
     expiration windows available; only the 6–9 DTE window is kept
   - This automatically excludes stocks without weekly options

2. **Add temporal features**
   - Day of week (0=Monday, 6=Sunday)
   - Restrict analysis to Thursdays (day 3) and Fridays (day 4)
   - These represent 7–8 DTE entries for next week's expiration

3. **Join stock price data**
   - `underlying_price` (Theta, intraday): used for moneyness calculation at quote time
   - `underlying_close` (yfinance): used as settlement price at expiry via date-keyed lookup
   - Both must be in the same price scale (enforced by step 0)

4. **Apply base filters**
   - Puts only (`right == 'PUT'`)
   - OTM only: moneyness between −20% and 0% (strike < underlying_price)
   - Bid > 0 (no market bid = untradeable; options with $0 bid cannot be sold)
   - *Deferred:* bid-ask spread check, volume ≥ 10, open interest ≥ 50 (to be added once base
     pipeline is validated)

5. **Dedup**
   - Multiple intraday quotes exist for the same (date, strike, expiry) — keep the last quote of the day
   - Ensures one row per tradeable opportunity

6. **Calculate key metrics**
   - **OTM%** = abs(moneyness) × 100 = (underlying_price − strike) / underlying_price × 100
   - **P&L** = bid − max(0, strike − close_at_expiry)
   - **Win** = boolean (P&L > 0)

7. **Assign OTM buckets**
   - 0.5% increments from 0% to 5% OTM
   - Bucket labels: "0.0-0.5%", "0.5-1.0%", "1.0-1.5%", etc.

**Output:** Per-ticker filtered dataset of tradeable weekly put opportunities with P&L calculated

---

### 1.2 Per-Stock Aggregation

For each ticker, for each OTM bucket, calculate:

**Sample Statistics:**
- Count of observations
- Date range covered (first to last occurrence)

**P&L Distribution:**
- Mean P&L
- Median P&L
- Standard deviation
- 5th percentile (downside risk)
- 25th, 75th, 95th percentiles
- Min and Max

**Win Metrics:**
- Win rate (% of trades with P&L > 0)
- Average win size (mean of profitable trades)
- Average loss size (mean of losing trades)
- Largest win, largest loss

**Expected Value:**
- Mean P&L (probability-weighted outcome)

**Confidence Indicators:**
- Sample size flags: High (30+), Medium (15-29), Low (5-14), Insufficient (<5)
- Time period covered (ensure not all clustered in one month)

**Output:** Lookup tables per ticker showing historical performance by OTM bucket

---

## Phase 2: Core Pricing Engine (Weeks 3-4)

### 2.1 Mode Detection & Position Tracking

**Position Database Schema:**

```sql
-- Active positions (long puts user currently holds)
CREATE TABLE active_positions (
    ticker VARCHAR(10) PRIMARY KEY,
    long_put_strike DECIMAL(10, 2),
    long_put_expiry DATE,
    long_put_cost DECIMAL(10, 2),
    entry_date DATE,
    weeks_active INT DEFAULT 0,
    total_premium_collected DECIMAL(10, 2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active'
);

-- Weekly trade history
CREATE TABLE weekly_trades (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10),
    short_put_strike DECIMAL(10, 2),
    short_put_expiry DATE,
    premium_collected DECIMAL(10, 2),
    entry_date DATE,
    close_date DATE,
    pl DECIMAL(10, 2),
    outcome VARCHAR(20)
);
```

**Workflow:**
1. Check if user has active position for ticker
2. If yes → Mode 2 (Weekly Selection)
3. If no → Mode 1 (Full Setup)

---

### 2.2 Mode 1: Full Setup (Initial Position)

**Inputs from user:**
- Ticker symbol (manually selected)
- Current stock price
- Account size
- Risk tolerance (default 3% max per trade)

**Step 1: Long Put Selection**

1. **Filter to 90-150 DTE puts**
   - Must expire after next earnings date
   - Focus on ~25 delta (as per book's guidance)

2. **Calculate efficiency metrics**
   - Cost per day of protection: premium / DTE
   - Protection per dollar: (stock_price - strike) / premium
   - Historical decay rate (if available)

3. **Rank by cost efficiency**
   - Balance protection level vs. cost
   - Highlight trade-offs (tighter spread = more cost)

4. **User selects long put**
   - Present top 3 options
   - User chooses or provides custom strike
   - Store in active_positions table

**Step 2: Weekly Short Put Selection**
- Proceed to 2.3 with selected long put

---

### 2.3 Mode 2: Weekly Selection (Primary Use Case)

**Inputs from user:**
- Ticker symbol (manually selected)
- System retrieves existing long put from database

**System workflow:**

1. **Fetch current options chain**
   - Get all weekly puts expiring 7-8 days out (next Friday)
   - Filter to OTM strikes only
   - **Filter to strikes ABOVE long put floor** (critical!)

2. **Calculate OTM% for each strike**
   - For each available strike, compute: (current_price - strike) / current_price × 100

3. **Look up historical performance**
   - Match each strike's OTM% to the appropriate bucket
   - Retrieve pre-calculated statistics from Phase 1

4. **Handle insufficient data**
   - If bucket has <15 samples, expand to neighboring buckets
   - Flag confidence level to user
   - Consider expanding to sector peers if very sparse

5. **Calculate risk with existing long put**
   - Max risk per spread = (short_strike - long_put_strike) × 100 - premium
   - Max contracts = (account_size × risk_pct) / max_risk
   - This is MORE accurate than generic calculation

6. **Rank strikes by composite score**
   - Weight multiple factors:
     - Expected value (40%)
     - Win rate (30%)
     - Downside protection (20%)
     - Sample confidence (10%)
   - Present top 3-5 options

7. **Show position context**
   - Display: weeks active, total premium collected, net P&L
   - Flag: if long put needs rolling soon (< 30 days)
   - Context: current IV rank, earnings proximity

**Output:** Ranked list of strike recommendations with:
- Historical stats
- Risk specific to user's long put
- Position progress (week X of 16)
- Net P&L to date

---

### 2.4 Batch Analysis Mode

**For users with multiple active positions:**

1. **Fetch all active positions**
   - Query active_positions table
   - Filter to positions with > 30 days remaining

2. **Analyze each position**
   - Run Mode 2 workflow for each ticker
   - Get top recommendation per position

3. **Rank opportunities**
   - Sort by score, IV rank, expected value
   - Flag positions to skip (low IV, low score)

4. **Present summary table**
   - Show all positions at once
   - User can drill into details or execute batch

**Output:** Dashboard view of all active positions with recommendations

---

## Phase 3: LLM Integration (Week 5)

### 3.1 Local LLM Setup

**Purpose:** Synthesize statistical output into plain English explanations

**Integration points:**

1. **Strike recommendation explanation**
   - Input: Statistical output from pricing engine
   - Output: Natural language summary of why strikes are ranked as they are

2. **Trade-off analysis**
   - Compare top recommendations
   - Explain what you gain/lose by choosing each option

3. **Risk narrative**
   - Translate percentiles into readable risk assessment
   - Contextualize historical performance

4. **Current market context** (if web search enabled)
   - Fetch recent news/events for the ticker
   - Note if current IV rank is elevated vs. historical
   - Flag any upcoming events (earnings, ex-dividend)

**Key principle:** LLM explains the math, doesn't replace it

---

### 3.2 Explanation Templates

**Structure for LLM prompts:**

```
You are explaining options pricing analysis to a trader.

Historical Data:
- 18 similar trades (1.0-1.5% OTM bucket)
- Win rate: 74%
- Expected P&L: +$0.82 per contract
- 5th percentile outcome: -$0.55
- Current IV rank: 68th percentile (elevated)

Task: Explain why selling the $73 put (1.4% OTM) is recommended
over the $72 put (2.7% OTM) and $74 put (ATM).

Be specific, reference the data, and highlight trade-offs.
```

**Output qualities:**
- Concise (2-3 paragraphs max)
- Data-driven (reference actual statistics)
- Actionable (clear recommendation with rationale)
- Risk-aware (acknowledge what could go wrong)

---

## Phase 4: User Interface (Week 6)

### 4.1 MVP Command-Line Interface

**Design principle:** Optimized for weekly routine (Mode 2), with full setup available when needed.

---

### 4.2 Mode 1: Full Setup (New Position)

**Workflow for starting a new position:**

```
$ python kaching_pricer.py --mode full

Enter ticker: SCHW
Current stock price: $74.00
Account size: $50,000
Max risk per trade (%): 3

Checking for existing position... None found.

════════════════════════════════════════════════════════
STEP 1: SELECT PROTECTIVE LONG PUT
════════════════════════════════════════════════════════

Recommended Long Puts (25 delta, 90-150 DTE):

1. $70 strike, 120 DTE ⭐ BEST VALUE
   Cost: $4.20 per contract
   Efficiency: $0.035/day
   Delta: 0.26
   
2. $68 strike, 115 DTE
   Cost: $3.10 per contract
   Efficiency: $0.027/day (cheaper but wider spread)
   Delta: 0.22
   
3. $72 strike, 125 DTE
   Cost: $5.40 per contract
   Efficiency: $0.043/day (tighter spread but pricier)
   Delta: 0.30

Select [1-3] or enter custom strike: 1

✓ Long put selected: $70 strike, 120 DTE, $4.20

════════════════════════════════════════════════════════
STEP 2: SELECT WEEKLY SHORT PUT
════════════════════════════════════════════════════════

Weekly Puts (8 DTE, above $70 floor):

1. $73 strike (1.4% OTM) - SCORE: 84/100 ⭐
   Premium: $0.95
   Historical: 74% win rate (18 similar trades)
   Expected P&L: +$0.82
   Max risk: $210 per spread ($73-$70-$0.95)
   Max contracts: 7
   
2. $72 strike (2.7% OTM) - SCORE: 78/100
   Premium: $0.68
   Historical: 81% win rate (12 similar trades)
   Expected P&L: +$0.65
   Max risk: $132 per spread
   Max contracts: 11

Select strike [1-2]: 1

════════════════════════════════════════════════════════
POSITION SUMMARY
════════════════════════════════════════════════════════

Ticker: SCHW
Long Put: $70 @ $4.20 (120 days)
Short Put: $73 @ $0.95 (8 days)
Contracts: 7

Initial Setup Cost: $29.40 ($4.20 × 7)
Weekly Income: $6.65 ($0.95 × 7)
Payback in: ~4.5 weeks

16-Week Projection:
  Total premium collected: $106.40
  Insurance cost: $29.40
  Net profit (if all expire): $77.00
  ROI: 262%

Save this position? [y/n]: y
✓ Position saved. Use 'kaching_pricer.py SCHW' for weekly updates.
```

---

### 4.3 Mode 2: Weekly Selection (Primary Use Case)

**Simple invocation - just ticker:**

```
$ python kaching_pricer.py SCHW

Analyzing SCHW...
✓ Found active position: $70 long put (97 days remaining)

Current: $74.00
Weeks active: 8/16
Premium collected: $6.40
Net P&L: +$2.20 (already profitable!)

════════════════════════════════════════════════════════
WEEKLY RECOMMENDATION
════════════════════════════════════════════════════════

$73 Strike - SCORE: 84/100 ⭐ STRONG BUY

  Premium: $0.95 (1.4% OTM)
  Max risk: $210 with your $70 floor
  Contracts: 7 (within risk limits)

  Historical (18 similar setups):
  ├─ Won: 13 times (74%) → avg +$0.87
  ├─ Lost: 5 times (26%) → avg -$0.32
  └─ Expected value: +$0.82

  Current conditions:
  ✓ IV Rank: 72nd percentile (elevated - good!)
  ✓ Earnings: Not for 47 days (clear)
  ✓ VIX: 18 (normal)

Alternative strikes:
  $72 (safer): 81% win rate, $0.68 premium
  $74 (riskier): 68% win rate, $1.28 premium

Sell $73 put? [y/n/more]: y

✓ Recorded. Week 9 starts.
```

---

### 4.4 Batch Mode (Multiple Positions)

**Quick overview of all active positions:**

```
$ python kaching_pricer.py --all

════════════════════════════════════════════════════════
KACHING WEEKLY ANALYSIS - Thursday, Jan 16, 2025
════════════════════════════════════════════════════════

Active Positions: 5

┌────────┬────────┬─────────┬─────────────────────────────┐
│ Ticker │ Floor  │ Week    │ Recommendation               │
├────────┼────────┼─────────┼─────────────────────────────┤
│ SCHW   │ $70    │ 8/16    │ $73 @ $0.95 (84) ⭐         │
│ MSFT   │ $380   │ 12/16   │ $390 @ $4.20 (81) ⭐        │
│ AAPL   │ $220   │ 5/16    │ $225 @ $2.80 (79)           │
│ GOOG   │ $165   │ 3/16    │ $168 @ $1.90 (76)           │
│ AMD    │ $130   │ 1/16    │ ⚠️  Skip - Low IV (42 pct)   │
└────────┴────────┴─────────┴─────────────────────────────┘

Total potential premium: $11.85/contract (4 positions)
Net P&L across all positions: +$18.50

Actions:
  [d] Details for specific ticker
  [e] Execute all recommended
  [s] Skip positions
  [q] Quit

Select: d

Enter ticker [SCHW/MSFT/AAPL/GOOG/AMD]: SCHW

[Shows detailed Mode 2 output for SCHW]
```

---

### 4.5 Position Management Commands

**Additional helper commands:**

```bash
# Check position status
$ python kaching_pricer.py --status SCHW

SCHW Position Status:
  Long Put: $70 (expires in 97 days)
  Weeks active: 8/16
  Premium collected: $6.40
  Long put cost: $4.20
  Net P&L: +$2.20 ✓

  Trade history:
  Week 1: $73 @ $0.85 → Expired worthless ✓
  Week 2: $73 @ $0.90 → Expired worthless ✓
  Week 3: $72 @ $0.70 → Expired worthless ✓
  Week 4: $74 @ $1.10 → Expired worthless ✓
  Week 5: $73 @ $0.88 → Bought back @ $0.15 ✓
  Week 6: $73 @ $0.92 → Expired worthless ✓
  Week 7: $72 @ $0.68 → Expired worthless ✓
  Week 8: $73 @ $0.82 → Expired worthless ✓

# List all positions
$ python kaching_pricer.py --list

Active positions:
  SCHW ($70 floor, 97 days, +$2.20)
  MSFT ($380 floor, 73 days, +$12.40)
  AAPL ($220 floor, 110 days, -$1.20)
  GOOG ($165 floor, 125 days, +$4.80)
  AMD ($130 floor, 139 days, +$0.50)

# Close position
$ python kaching_pricer.py --close SCHW

Close SCHW position?
  Long put: $70 (current value ~$2.10)
  Weeks held: 8
  Premium collected: $6.40
  If closed now: +$4.30 profit

Confirm close? [y/n]: y
✓ Position closed.

# Roll long put
$ python kaching_pricer.py --roll SCHW

Current long put: $70 (27 days remaining)
⚠️  Time to roll!

Roll options:
1. $72 strike, 120 DTE → $4.80 (cost $2.70 to roll)
2. $70 strike, 120 DTE → $4.20 (cost $2.10 to roll)
3. $68 strike, 120 DTE → $3.40 (cost $1.30 to roll)

Select: 2
✓ Rolled to new $70 put, 120 DTE
```

---

### 4.6 Enhanced Features (Optional)

**If time permits:**

1. **Quick stats**
```bash
$ python kaching_pricer.py --stats

Overall Performance:
  Total positions: 5 active, 12 closed
  Win rate: 76% (89/117 weekly trades)
  Total premium collected: $2,847
  Total cost: $892 (long puts)
  Net profit: $1,955
  ROI: 219%
  
  Best performer: MSFT (+$420)
  Worst performer: AAPL (-$45)
```

2. **Comparison mode**
```bash
$ python kaching_pricer.py --compare SCHW MSFT AAPL

Compare three tickers side-by-side
[Shows table of recommendations]
```

3. **Historical viewer**
```bash
$ python kaching_pricer.py --history SCHW

Show the 18 actual historical trades that inform the $73 recommendation
[Detailed list with dates, outcomes, market conditions]
```

4. **Alerts**
```bash
$ python kaching_pricer.py --alert

Set up alerts:
  ✓ Email when IV rank > 70th percentile
  ✓ Notify when long put < 30 days (time to roll)
  ✓ Weekly summary every Thursday 9am
```

---

## Phase 5: Validation & Refinement (Week 7-8)

### 5.1 Backtest Validation

**Test the tool's recommendations retrospectively:**

1. **Select 10 liquid stocks** (AAPL, MSFT, SCHW, etc.)

2. **For each week in last 3 months** (not in training data if possible):
   - Run the pricing tool as if it were that Thursday
   - Record what it would have recommended
   - Compare to actual outcomes the following week

3. **Calculate accuracy metrics:**
   - Did top recommendation win more than historical win rate?
   - Was expected value prediction accurate?
   - Were there systematic biases?

4. **Identify failure modes:**
   - What conditions caused recommendations to fail?
   - Were there missing filters or edge cases?

**Goal:** Ensure tool's statistics translate to real-world performance

---

### 5.2 Edge Case Handling

**Build robustness for:**

1. **New stocks with limited history**
   - Clear warnings about low confidence
   - Option to include sector peer data
   - Require minimum thresholds

2. **Market regime changes**
   - Detect when current IV rank is extreme vs. historical period
   - Flag when current conditions differ significantly
   - Adjust confidence levels accordingly

3. **Corporate actions**
   - Flag stocks near earnings (shouldn't appear in weekly data anyway)
   - Detect dividend dates
   - ~~Handle splits in historical data~~ → **RESOLVED:** split price mismatch between Theta and
     yfinance is detected and excluded via the `underlying_price / underlying_close` ratio filter
     in Phase 1.1a step 0. No manual split tracking needed.

4. **Data quality issues**
   - Identify and exclude obvious errors (negative premiums, etc.)
   - Handle missing data gracefully
   - Validate strike/price relationships

---

## Phase 6: Enhancement Path (Future)

### 6.1 Near-Term Enhancements (Months 2-3)

1. **Conditional performance analysis**
   - Segment historical data by market conditions
   - "When stock was uptrending, win rate improved to 82%"
   - Add technical indicators to historical data

2. **Multi-factor scoring**
   - Combine OTM bucket statistics with current Greeks
   - Weight factors based on user preferences
   - Allow customization of scoring algorithm

3. **Live paper trading tracker**
   - Record tool recommendations in real-time
   - Track actual outcomes
   - Build personalized statistics over time

4. **Regime detection**
   - Identify current market regime (bull/bear/sideways)
   - Filter historical data to similar regimes
   - Adjust expectations accordingly

---

### 6.2 Long-Term Enhancements (Months 4-6)

1. **Stock screening module** (Phase 2 from original plan)
   - Automated technical analysis
   - Identify stocks meeting "edge" criteria
   - Rank candidates by strategy compatibility
   - Feed directly into pricing tool

2. **Probabilistic modeling**
   - Monte Carlo simulations for price distribution
   - Combine with empirical data for confidence intervals
   - Stress testing ("what if VIX spikes?")

3. **Portfolio-level optimization**
   - Manage multiple positions simultaneously
   - Sector diversification constraints
   - Correlation-aware position sizing
   - Total portfolio risk management

4. **Machine learning enhancements**
   - Train classifier to predict bucket performance
   - Feature importance analysis
   - Ensemble with empirical distributions

---

## Success Metrics

### MVP Success (End of Week 6):
- [ ] Mode 1 (Full Setup) works: Can recommend both long and short puts for new positions
- [ ] Mode 2 (Weekly Selection) works: Can recommend weekly puts given existing long put
- [ ] Batch mode works: Can analyze multiple active positions at once
- [ ] Recommendations based on 1 year of actual historical P&L data
- [ ] Clear presentation of win rates, expected values, risk metrics
- [ ] Position tracking works: Stores and retrieves active positions correctly
- [ ] LLM provides intelligible explanations for both modes
- [ ] Confidence flags for data quality
- [ ] Can complete typical Thursday morning routine in < 5 minutes

### Validation Success (End of Week 8):
- [ ] Tool's recommendations match or exceed historical win rates
- [ ] No systematic biases detected in backtesting
- [ ] Position tracking accurate across multiple weeks
- [ ] Net P&L calculations correct (premium collected vs long put cost)
- [ ] Edge cases handled gracefully (low IV, sparse data, near expiry)
- [ ] User can trust the statistics presented

### Production Ready (Month 3):
- [ ] Used successfully for 10+ live trades across multiple positions
- [ ] Tool's predictions align with actual outcomes
- [ ] Position tracking maintained correctly over multiple cycles
- [ ] Rolling logic works smoothly (transitioning to new long puts)
- [ ] Batch analysis saves significant time (vs manual analysis)
- [ ] Integration with broker API for real-time data (optional)
- [ ] Automated alerts for high IV setups or roll reminders

---

## Typical User Workflows

### Workflow A: Starting a New Position (Mode 1)

**Frequency:** Once per 120 days per stock

1. User identifies stock with "edge" (uptrend, consolidation)
2. Runs: `python kaching_pricer.py --mode full`
3. Enters ticker, account size, risk tolerance
4. Reviews long put recommendations (3 options)
5. Selects long put (typically 25 delta, 120 DTE)
6. Reviews weekly short put recommendations (3-5 options)
7. Selects short put based on risk/reward preference
8. Tool saves position to database
9. Trade executed via broker

**Time investment:** 5-10 minutes

---

### Workflow B: Weekly Routine (Mode 2)

**Frequency:** Every Thursday/Friday for each active position

**Single Position:**
1. Runs: `python kaching_pricer.py SCHW`
2. Tool auto-detects existing $70 long put
3. Reviews top recommendation with historical stats
4. Checks IV rank, position progress, net P&L
5. Executes trade (or selects alternative strike)

**Time investment:** 1-2 minutes per position

**Multiple Positions (Batch):**
1. Runs: `python kaching_pricer.py --all`
2. Reviews dashboard with all 5 positions
3. Identifies which positions have good setups this week
4. Drills into details for positions of interest
5. Skips positions with low IV or poor scores
6. Executes recommended trades

**Time investment:** 3-5 minutes for 5-7 positions

---

### Workflow C: Position Management

**Rolling Long Put (Every ~90 days per position):**
1. Tool alerts: "SCHW long put expires in 28 days"
2. Runs: `python kaching_pricer.py --roll SCHW`
3. Reviews roll options (new strikes, costs)
4. Selects new long put
5. Executes roll via broker
6. Tool updates position database

**Time investment:** 3-5 minutes

**Closing Position (When stock loses edge):**
1. User notices SCHW broke major support
2. Runs: `python kaching_pricer.py --close SCHW`
3. Reviews position summary (weeks held, net P&L)
4. Confirms close
5. Executes via broker (sell long put, buy back short put if needed)
6. Tool archives position

**Time investment:** 2-3 minutes

---

### Workflow D: Performance Review

**Weekly/Monthly Check:**
1. Runs: `python kaching_pricer.py --stats`
2. Reviews overall performance metrics
3. Identifies best/worst performers
4. Adjusts strategy if needed (e.g., tighten strikes, reduce positions)

**Time investment:** 5-10 minutes monthly

---

## Technical Architecture

### Data Layer
- **Storage:** SQLite or PostgreSQL for historical data
- **Schema:** Tables for options_history, stocks_history, bucket_statistics
- **Indexing:** By ticker, date, OTM_bucket for fast lookups

### Computation Layer
- **Language:** Python (pandas for data manipulation)
- **Statistical libraries:** numpy, scipy for distributions
- **Caching:** Pre-compute bucket statistics, refresh weekly

### LLM Layer
- **Model:** Local LLM (Llama, Mistral, etc.) via Ollama or similar
- **Integration:** API calls with structured prompts
- **Fallback:** Tool works without LLM (just shows raw stats)

### Interface Layer
- **MVP:** Command-line Python script
- **Future:** Web interface (Flask/Streamlit) or desktop GUI

---

## Risk Considerations & Disclaimers

### What This Tool Does:
✅ Provides historical performance statistics for specific OTM buckets
✅ Calculates risk metrics based on spread structures
✅ Ranks strikes by empirical outcomes
✅ Explains trade-offs between options

### What This Tool Does NOT Do:
❌ Predict future stock prices
❌ Guarantee any particular outcome
❌ Replace human judgment on stock selection
❌ Account for black swan events outside historical data
❌ Provide financial advice (informational only)

### User Responsibilities:
- Select stocks with genuine "edge" (uptrend, consolidation)
- Monitor positions actively
- Follow trading plan risk limits
- Understand maximum loss scenarios
- Exit when stock "loses edge"

### Data Limitations:
- 1 year may not capture all market regimes
- Past performance doesn't guarantee future results
- Low sample buckets have high uncertainty
- Historical data reflects specific period characteristics

---

## Implementation Checklist

### Week 1-2: Data Foundation
- [ ] Acquire 1 year of options data (ThetaData or alternative)
- [ ] Acquire corresponding stock price data (ThetaData or yfinance)
- [ ] Design database schema (include active_positions and weekly_trades tables)
- [ ] Write ETL pipeline for data cleaning
- [ ] Apply filters (weekly options, Thursday/Friday, price limits)
- [ ] Calculate OTM%, P&L for all records
- [ ] Assign OTM buckets
- [ ] Generate per-ticker, per-bucket aggregation tables
- [ ] Validate data quality (spot check 5-10 stocks)

### Week 3-4: Pricing Engine
- [ ] Build position tracking system (database tables)
- [ ] Build mode detection logic (check for existing positions)
- [ ] Build Mode 1: Long put recommendation function
- [ ] Build Mode 2: Weekly short put recommendation function (with long put floor)
- [ ] Build combination optimizer (when in Mode 1)
- [ ] Implement confidence scoring
- [ ] Handle sparse data cases (bucket expansion, sector peers)
- [ ] Add position sizing logic (respecting existing long put)
- [ ] Build batch analysis for multiple positions
- [ ] Test on 5 different stocks with varying data quality

### Week 5: LLM Integration
- [ ] Set up local LLM (Ollama + Llama/Mistral)
- [ ] Design prompt templates for both modes
- [ ] Build LLM explanation pipeline
- [ ] Add position context to explanations (weeks active, net P&L)
- [ ] Test explanation quality on sample outputs
- [ ] Add fallback for when LLM unavailable

### Week 6: User Interface
- [ ] Build CLI application with mode detection
- [ ] Implement Mode 1 workflow (full setup)
- [ ] Implement Mode 2 workflow (weekly selection)
- [ ] Build batch mode (--all flag)
- [ ] Add position management commands (--status, --list, --close, --roll)
- [ ] Implement quick mode (just ticker, auto-detect position)
- [ ] Format output for readability (tables, colors, symbols)
- [ ] Add error handling and user guidance
- [ ] Test complete workflow end-to-end for both modes

### Week 7-8: Validation
- [ ] Design backtesting framework
- [ ] Run retrospective tests on 10 stocks
- [ ] Validate Mode 2 recommendations against actual outcomes
- [ ] Analyze accuracy of tool predictions
- [ ] Test position tracking across multiple weeks
- [ ] Identify and fix systematic issues
- [ ] Document edge cases and limitations
- [ ] Write user guide covering both modes

### Optional Enhancements (Post-MVP)
- [ ] Add performance statistics (--stats)
- [ ] Build historical trade viewer
- [ ] Add comparison mode for multiple tickers
- [ ] Implement alert system (email/SMS for high IV, roll reminders)
- [ ] Create web interface (Flask/Streamlit)
- [ ] Add data export (CSV, Excel)
- [ ] Build visualization dashboard
- [ ] Add paper trading mode for validation

---

## Next Steps

1. **Acquire data:** Confirm data source and download 1 year of EOD options data
2. **Set up environment:** Python environment with pandas, numpy, scipy, sqlite3
3. **Design schema:** Sketch out database tables for efficient querying
4. **Start ETL:** Begin data cleaning and transformation pipeline
5. **Build incrementally:** Get one ticker working end-to-end before scaling

---

## Notes & Open Questions

**Questions to resolve:**

1. **Data source specifics:**
   - Confirm exact fields available in your options data
   - Verify you have both bid and ask (not just mid or last)
   - Check if IV rank is pre-calculated or needs computation

2. **Technical indicators:**
   - How will you determine "uptrend" / "consolidation"?
   - Will you add these to historical data retroactively?
   - Or only use for current conditions flagging?

3. **Minimum viable thresholds:**
   - What's your minimum acceptable sample size? (15? 20? 30?)
   - How much will you loosen constraints for sparse data?
   - When do you refuse to make a recommendation?

4. **User workflow:**
   - Will user run this weekly? Daily?
   - Integration with broker for real-time option chains?
   - Or manual input of current options prices?

5. **Long put lifecycle:**
   - Tool recommends long put once per 120-day cycle
   - How to track when to roll/replace long put?
   - Build reminder system?

---

**Document Version:** 1.1
**Last Updated:** 2026-02-22
**Status:** Phase 1.1a in progress — pipeline implemented in `main.py`, per-ticker aggregation (Phase 1.2) next