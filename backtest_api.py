# backtest_api.py
import yfinance as yf
import pandas as pd
from typing import List  # NEW
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

START_CASH = 10_000

app = FastAPI(
    title="SMA Backtest API",
    description="Simple moving-average crossover backtester using Yahoo Finance data",
    version="1.0.0",
)

# --- CORS (so your Next.js/Loveable frontend can call this) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # in production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic models ----------

class BacktestRequest(BaseModel):
    ticker: str = Field(..., example="AAPL")
    fast_window: int = Field(..., gt=0, example=20)
    slow_window: int = Field(..., gt=0, example=50)


class Trade(BaseModel):
    side: str
    date: str
    price: float
    shares: int


class BacktestResponse(BaseModel):
    ticker: str
    fast_window: int
    slow_window: int
    final_value: float
    total_return_pct: float
    dates: list[str]
    equity_curve: list[float]
    trades: list[Trade]


# ---------- NEW models for multi-strategy endpoint ----------

class StrategyParams(BaseModel):
    fast_window: int
    slow_window: int


class StrategySummary(BaseModel):
    fast_window: int
    slow_window: int
    final_value: float
    total_return_pct: float


class MultiBacktestRequest(BaseModel):
    ticker: str
    strategies: List[StrategyParams]


class MultiBacktestResponse(BaseModel):
    ticker: str
    strategies: List[StrategySummary]
    best_strategy: StrategySummary


# ---------- Core backtest logic (adapted from your code) ----------

def run_backtest(ticker: str, fast_window: int, slow_window: int):
    # Download 5 years of daily data
    raw_data = yf.download(ticker, period="5y", interval="1d", progress=False)

    if raw_data.empty:
        raise ValueError(f"No data found for ticker '{ticker}'.")

    prices = raw_data[["Close"]].dropna().copy()

    df = prices.copy()

    # Moving averages
    df["ma_fast"] = df["Close"].rolling(fast_window).mean()
    df["ma_slow"] = df["Close"].rolling(slow_window).mean()
    df = df.dropna().copy()

    if df.empty:
        raise ValueError(
            "Not enough data points to compute moving averages with "
            f"fast_window={fast_window}, slow_window={slow_window}."
        )

    # Signals
    df["signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)
    df["position_change"] = df["signal"].diff().fillna(0)

    # Backtest state
    cash = START_CASH
    shares = 0
    equity_values = []  # portfolio value each day
    trades = []         # list of individual trades

    # Loop through each day
    for i in range(len(df)):
        price = float(df["Close"].iloc[i])
        pos_change = float(df["position_change"].iloc[i])
        date = df.index[i]

        # BUY: go from 0 -> 1
        if pos_change == 1 and cash > 0:
            new_shares = int(cash // price)
            if new_shares > 0:
                cash -= new_shares * price
                shares += new_shares
                trades.append({
                    "side": "BUY",
                    "date": date,
                    "price": price,
                    "shares": new_shares,
                })

        # SELL: go from 1 -> 0
        elif pos_change == -1 and shares > 0:
            cash += shares * price
            trades.append({
                "side": "SELL",
                "date": date,
                "price": price,
                "shares": shares,
            })
            shares = 0

        # Track portfolio value
        portfolio_value = cash * 1.0 + shares * price
        equity_values.append(portfolio_value)

    # Build equity curve using df.index as the dates
    equity_df = pd.DataFrame({"value": equity_values}, index=df.index)
    final_value = float(equity_df["value"].iloc[-1])
    total_return = (final_value / START_CASH - 1) * 100.0

    # Convert to JSON-serializable forms
    dates = [d.strftime("%Y-%m-%d") for d in equity_df.index]
    trades_serializable = [
        {
            "side": t["side"],
            "date": t["date"].strftime("%Y-%m-%d"),
            "price": float(t["price"]),
            "shares": int(t["shares"]),
        }
        for t in trades
    ]

    return {
        "ticker": ticker.upper(),
        "fast_window": fast_window,
        "slow_window": slow_window,
        "final_value": final_value,
        "total_return_pct": total_return,
        "dates": dates,
        "equity_curve": equity_values,
        "trades": trades_serializable,
    }


# ---------- Single-strategy FastAPI endpoint ----------

@app.post("/backtest", response_model=BacktestResponse)
def backtest(req: BacktestRequest):
    if req.fast_window >= req.slow_window:
        raise HTTPException(
            status_code=400,
            detail="fast_window must be smaller than slow_window.",
        )

    try:
        result = run_backtest(req.ticker, req.fast_window, req.slow_window)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


# ---------- NEW multi-strategy endpoint ----------

@app.post("/multi-backtest", response_model=MultiBacktestResponse)
def multi_backtest(req: MultiBacktestRequest):
    if not req.strategies:
        raise HTTPException(status_code=400, detail="No strategies provided.")

    summaries: List[StrategySummary] = []

    for s in req.strategies:
        if s.fast_window >= s.slow_window:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"fast_window must be smaller than slow_window "
                    f"(got {s.fast_window}, {s.slow_window})."
                ),
            )

        result = run_backtest(req.ticker, s.fast_window, s.slow_window)

        summaries.append(
            StrategySummary(
                fast_window=result["fast_window"],
                slow_window=result["slow_window"],
                final_value=result["final_value"],
                total_return_pct=result["total_return_pct"],
            )
        )

    # Pick best by highest total_return_pct
    best = max(summaries, key=lambda x: x.total_return_pct)

    return MultiBacktestResponse(
        ticker=req.ticker.upper(),
        strategies=summaries,
        best_strategy=best,
    )