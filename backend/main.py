"""
VQI Quantum Option Pricing — FastAPI Backend
=============================================
Wraps QAEFINAL.py pricing functions behind a REST API.
Also serves the frontend static files so everything runs on one port.

Run:
    cd backend
    uvicorn main:app --reload --port 8000

Then visit: http://localhost:8000
"""

import time
import sys
import numpy as np
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Make sure QAEFINAL is importable from this directory
sys.path.insert(0, str(Path(__file__).parent))
import QAEFINAL


app = FastAPI(title="VQI Quantum Option Pricing API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
#  REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────
class PriceRequest(BaseModel):
    option_style: str = Field(..., description="european, american, or asian")
    option_type:  str = Field(..., description="call or put")
    S:   float = Field(..., gt=0,          description="Stock price ($)")
    K:   float = Field(..., gt=0,          description="Strike price ($)")
    vol: float = Field(..., gt=0, le=5.0,  description="Annualized volatility (e.g. 0.2 = 20%)")
    r:   float = Field(...,                description="Risk-free rate (e.g. 0.05 = 5%)")
    T:   float = Field(..., gt=0,          description="Time to maturity in years")
    D:            float = Field(default=0.0, ge=0,  description="Discrete cash dividend ($). 0 = none.")
    ex_div_step:  int   = Field(default=4,  ge=1,   description="Step at which dividend is paid")


# ─────────────────────────────────────────────────────────────
#  PRICING ENDPOINT
# ─────────────────────────────────────────────────────────────
@app.post("/api/price")
def price_option(req: PriceRequest):
    """
    Run the quantum option pricing engine for the given parameters.
    European and Asian use QAE; American uses classical backward induction.
    NOTE: European QAE may take 15–60 seconds on a laptop due to simulation overhead.
    """
    style = req.option_style.lower().strip()
    call  = req.option_type.lower().strip() == "call"

    if style not in {"european", "american", "asian"}:
        raise HTTPException(status_code=400, detail=f"Unknown option_style '{style}'. Use european, american, or asian.")

    start = time.time()
    try:
        if style == "european":
            result = QAEFINAL.price_european(
                req.S, req.K, req.vol, req.r, req.T, call,
                D=req.D, ex_div_step=req.ex_div_step,
            )
        elif style == "american":
            result = QAEFINAL.price_american(
                req.S, req.K, req.vol, req.r, req.T, call,
                D=req.D, ex_div_step=req.ex_div_step,
            )
        else:  # asian
            result = QAEFINAL.price_asian(
                req.S, req.K, req.vol, req.r, req.T, call,
                D=req.D, ex_div_step=req.ex_div_step,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pricing engine error: {exc}")

    result["execution_time_ms"] = round((time.time() - start) * 1000)
    return result


# ─────────────────────────────────────────────────────────────
#  TICKER QUOTE ENDPOINT
# ─────────────────────────────────────────────────────────────
@app.get("/api/quote/{ticker}")
def get_quote(ticker: str):
    """
    Fetch current price and 30-day annualised historical volatility for a ticker.
    Uses yfinance. Returns: price, volatility (decimal), company name.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance not installed. Run: pip install yfinance")

    t = yf.Ticker(ticker.upper())

    hist = t.history(period="30d")
    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No data found for ticker '{ticker.upper()}'. Check the symbol and try again.")

    # Current price: last closing price
    price = round(float(hist["Close"].iloc[-1]), 2)

    # 30-day annualised historical volatility from daily log returns
    log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    vol = round(float(log_returns.std() * np.sqrt(252)), 4)   # annualised, as decimal

    # Company name (best-effort)
    info = t.info
    name = info.get("shortName") or info.get("longName") or ticker.upper()

    return {"ticker": ticker.upper(), "name": name, "price": price, "volatility": vol}


# ─────────────────────────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
#  SERVE FRONTEND  (must be registered last — catch-all mount)
# ─────────────────────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
