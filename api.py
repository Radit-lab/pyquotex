import os
import time
import asyncio
import logging
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from pyquotex.stable_api import Quotex
from pyquotex.config import credentials as pq_credentials
from pyquotex.utils.processor import process_candles, get_color

logger = logging.getLogger("api")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="PyQuotex API", version="1.0.0")


class Candle(BaseModel):
    asset: str
    time: int
    date: str
    time_hm: str
    open: float
    close: float
    low: float
    high: float
    ticks: Optional[int] = None
    color: Optional[str] = None


class CandlesResponse(BaseModel):
    asset: str
    period: int
    count: int
    candles: List[Candle]


class QuotexService:
    def __init__(self):
        self.client: Optional[Quotex] = None
        self._lock = asyncio.Lock()

    async def init(self):
        # Credentials from env or local credentials function
        email = os.getenv("PYQUOTEX_EMAIL")
        password = os.getenv("PYQUOTEX_PASSWORD")
        if not email or not password:
            try:
                email, password = pq_credentials()
            except Exception:
                pass
        if not email or not password:
            raise RuntimeError("Credentials not provided. Set PYQUOTEX_EMAIL and PYQUOTEX_PASSWORD or configure credentials().")

        self.client = Quotex(email=email, password=password, lang="pt")
        ok, reason = await self.client.connect()
        if not ok:
            # try once more after cleaning session if file exists
            try:
                if os.path.exists("session.json"):
                    os.remove("session.json")
            except Exception:
                pass
            await asyncio.sleep(1)
            ok, reason = await self.client.connect()
        if not ok:
            raise RuntimeError(f"Failed to connect to Quotex: {reason}")
        logger.info("Quotex client connected for API.")

    async def ensure_connected(self):
        if not self.client:
            raise RuntimeError("Quotex client not initialized")
        if not await self.client.check_connect():
            ok, reason = await self.client.connect()
            if not ok:
                raise RuntimeError(f"Reconnection failed: {reason}")

    async def fetch_candles(self, asset: str, period: int, offset: int) -> List[Dict[str, Any]]:
        async with self._lock:
            await self.ensure_connected()
            end_from_time = time.time()
            candles = await self.client.get_candles(asset, end_from_time, offset, period)
        if not candles:
            return []
        if not candles[0].get("open"):
            candles = process_candles(candles, period)
        # enrich with color and human-readable date/time
        for c in candles:
            c["asset"] = asset
            if "open" in c and "close" in c:
                c["color"] = get_color(c)
            # add date as YYYY-MM-DD and time_hm as HH:MM from epoch seconds
            try:
                ts = int(c.get("time", 0))
                lt = time.localtime(ts)
                c["date"] = time.strftime("%Y-%m-%d", lt)
                c["time_hm"] = time.strftime("%H:%M", lt)
            except Exception:
                c["date"] = "1970-01-01"
                c["time_hm"] = "00:00"
        return candles


service = QuotexService()


@app.on_event("startup")
async def on_startup():
    await service.init()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/candles/last", response_model=CandlesResponse)
async def get_last_candles(
    asset: str = Query(..., description="Asset symbol, e.g., EURUSD_otc"),
    count: int = Query(50, ge=1, le=2000, description="Number of latest candles to fetch"),
    period: int = Query(60, ge=5, description="Candle period in seconds (e.g., 60 for 1 minute)")
):
    try:
        offset = count * period
        candles = await service.fetch_candles(asset, period, offset)
        # slice last N to return exactly requested count if server returned more
        candles = candles[-count:]
        return {
            "asset": asset,
            "period": period,
            "count": len(candles),
            "candles": candles,
        }
    except Exception as e:
        logger.exception("Error fetching last candles")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/candles/range", response_model=CandlesResponse)
async def get_candles_range(
    asset: str = Query(..., description="Asset symbol, e.g., EURUSD_otc"),
    period: int = Query(60, ge=5, description="Candle period in seconds"),
    offset: int = Query(3600, ge=1, description="Offset in seconds to fetch candles from now backwards")
):
    try:
        candles = await service.fetch_candles(asset, period, offset)
        return {
            "asset": asset,
            "period": period,
            "count": len(candles),
            "candles": candles,
        }
    except Exception as e:
        logger.exception("Error fetching range candles")
        raise HTTPException(status_code=500, detail=str(e))


# To run: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
