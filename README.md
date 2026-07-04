# SMA Backtest API

A FastAPI service that backtests simple moving-average crossover strategies against real historical price data pulled from Yahoo Finance.

## What this is

Give it a ticker and two window lengths (a fast SMA and a slow SMA), and it runs a day-by-day backtest: buy when the fast average crosses above the slow average, sell when it crosses back below, starting from $10,000 in cash. It returns the full equity curve, every trade taken, and the final return — enough to plot and evaluate the strategy without doing the simulation client-side.

There are two endpoints:

- `POST /backtest` — runs a single fast/slow window pair on one ticker.
- `POST /multi-backtest` — runs several fast/slow pairs on the same ticker in one call and returns the best-performing combination by total return. Useful for a quick parameter sweep without round-tripping to the API once per pair.

The backtest logic itself is straightforward and deliberately readable over clever:

1. Pull 5 years of daily closes for the ticker via `yfinance`.
2. Compute rolling fast and slow SMAs with pandas.
3. Generate a signal (1 when fast > slow, 0 otherwise) and detect crossovers from the day-over-day change in that signal.
4. Walk through the price series day by day: on a buy signal, put all available cash into whole shares; on a sell signal, liquidate the full position. Track portfolio value (cash + shares × price) every day to build the equity curve.
5. Serialize dates, the equity curve, and the trade log to JSON.

CORS is wide open (`allow_origins=["*"]`) since this is meant to be called from a frontend (Next.js, Loveable, etc.) during development — tighten it before deploying anywhere public.

## Tech stack

- FastAPI + Pydantic for the API layer and request/response validation
- yfinance for historical price data
- pandas for rolling-window calculations
- uvicorn as the ASGI server

## Getting started

```bash
pip install -r requirements.txt
uvicorn backtest_api:app --reload
```

The API will be live at `http://127.0.0.1:8000`, with interactive docs at `http://127.0.0.1:8000/docs`.

Example request to `/backtest`:

```json
{
  "ticker": "AAPL",
  "fast_window": 20,
  "slow_window": 50
}
```

## Project structure

```
backtest_api.py      # FastAPI app: models, backtest engine, and both endpoints
requirements.txt      # fastapi, uvicorn, yfinance, pandas, numpy
HOW TO RUN.txt         # quick local run instructions
```

## Limitations

- No transaction costs, slippage, or fractional shares — fills are instant at the daily close price
- Single-asset only; no portfolio-level backtesting across multiple tickers at once
- 5 years of daily data is hardcoded; not configurable per request yet
- No persistence — every request re-downloads data from Yahoo Finance, so repeated calls for the same ticker aren't cached

## Possible extensions

- Configurable date ranges and data intervals instead of a fixed 5-year daily window
- Transaction cost / slippage modeling
- Additional strategies beyond SMA crossover (RSI, MACD, mean reversion)
- Caching layer for repeated ticker requests
