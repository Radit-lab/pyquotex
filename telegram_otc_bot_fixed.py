#!/usr/bin/env python3
"""
Fixed Telegram OTC Bot for PyQuotex - REDOX v10.1
Sequential monitoring with reversal logic
"""

import os
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass

from telegram import Bot
from dotenv import load_dotenv
from pyquotex.stable_api import Quotex

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CandleData:
    open: float
    high: float
    low: float
    close: float
    timestamp: int

class TelegramOTCBot:
    OTC_PAIRS = [
        "AUDNZD_otc", "AXP_otc", "BA_otc", "BRLUSD_otc", "BTCUSD_otc", 
        "CADCHF_otc", "EURNZD_otc", "FB_otc", "NZDCAD_otc", "NZDCHF_otc", 
        "NZDJPY_otc", "PFE_otc", "UKBrent_otc", "USCrude_otc", "USDARS_otc", 
        "USDBDT_otc", "USDCOP_otc", "USDDZD_otc", "USDEGP_otc", "USDIDR_otc", 
        "USDINR_otc", "USDJPY_otc", "USDMXN_otc", "USDNGN_otc", "USDPHP_otc", 
        "USDPKR_otc", "USDTRY_otc", "USDZAR_otc", "XAGUSD_otc", "XAUUSD_otc"
    ]
    
    PAIR_NAMES = {
        "AUDNZD_otc": "AUD/NZD", "AXP_otc": "American Express", "BA_otc": "Boeing",
        "BRLUSD_otc": "USD/BRL", "BTCUSD_otc": "Bitcoin", "CADCHF_otc": "CAD/CHF",
        "EURNZD_otc": "EUR/NZD", "FB_otc": "Facebook", "NZDCAD_otc": "NZD/CAD",
        "NZDCHF_otc": "NZD/CHF", "NZDJPY_otc": "NZD/JPY", "PFE_otc": "Pfizer",
        "UKBrent_otc": "UK Brent", "USCrude_otc": "US Crude", "USDARS_otc": "USD/ARS",
        "USDBDT_otc": "USD/BDT", "USDCOP_otc": "USD/COP", "USDDZD_otc": "USD/DZD",
        "USDEGP_otc": "USD/EGP", "USDIDR_otc": "USD/IDR", "USDINR_otc": "USD/INR",
        "USDJPY_otc": "USD/JPY", "USDMXN_otc": "USD/MXN", "USDNGN_otc": "USD/NGN",
        "USDPHP_otc": "USD/PHP", "USDPKR_otc": "USD/PKR", "USDTRY_otc": "USD/TRY",
        "USDZAR_otc": "USD/ZAR", "XAGUSD_otc": "Silver", "XAUUSD_otc": "Gold"
    }
    
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.bot = Bot(token=self.telegram_token) if self.telegram_token else None
        self.quotex_client = None
        
    async def init_quotex(self) -> bool:
        try:
            self.quotex_client = Quotex()
            success, reason = await self.quotex_client.connect()
            if success:
                logger.info("Connected to Quotex")
                return True
            else:
                logger.error(f"Quotex connection failed: {reason}")
                return False
        except Exception as e:
            logger.error(f"Quotex init error: {e}")
            return False
    
    async def get_candles(self, pair: str, count: int = 4) -> Optional[List[CandleData]]:
        try:
            if not self.quotex_client:
                return None
            
            end_time = time.time()
            offset = count * 60
            
            candles_raw = await self.quotex_client.get_candles(
                asset=pair,
                end_from_time=end_time,
                offset=offset,
                period=60
            )
            
            if not candles_raw:
                return None
            
            candles = []
            for candle in candles_raw[-count:]:
                candles.append(CandleData(
                    open=float(candle.get('open', 0)),
                    high=float(candle.get('high', 0)),
                    low=float(candle.get('low', 0)),
                    close=float(candle.get('close', 0)),
                    timestamp=int(candle.get('time', 0))
                ))
            
            return candles
            
        except Exception as e:
            logger.error(f"Error getting candles for {pair}: {e}")
            return None
    
    def analyze_reversal(self, candles: List[CandleData]) -> Optional[Tuple[str, float]]:
        if len(candles) < 4:
            return None
        
        # Check if last 4 candles are same direction
        directions = []
        for candle in candles:
            if candle.close > candle.open:
                directions.append("CALL")
            elif candle.close < candle.open:
                directions.append("PUT")
            else:
                directions.append("NEUTRAL")
        
        # If all 4 candles are same direction, predict reversal
        if len(set(directions)) == 1 and directions[0] != "NEUTRAL":
            reversal_direction = "PUT" if directions[0] == "CALL" else "CALL"
            return reversal_direction, candles[-1].close
        
        return None
    
    def format_signal(self, pair: str, direction: str, price: float) -> str:
        name = self.PAIR_NAMES.get(pair, pair)
        time_str = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")
        color = "[GREEN]" if direction == "CALL" else "[RED]"
        
        return f"""======== REDOX v10.1 ========
PAIR: {name}
TIME: {time_str}
DIRECTION: {color} {direction}
PRICE: {price:.5f}
EXPIRY: M1
============================="""
    
    async def send_message(self, message: str) -> bool:
        print(f"\n{message}\n")
        
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=message)
                logger.info("Message sent to Telegram")
                return True
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
        
        # Log to file
        try:
            with open("signals.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - {message}\n\n")
        except Exception as e:
            logger.error(f"Log error: {e}")
        
        return True
    
    async def evaluate_result(self, pair: str, direction: str) -> str:
        logger.info(f"Waiting 60s to evaluate {pair} {direction}...")
        await asyncio.sleep(60)
        
        # Check first candle
        candles = await self.get_candles(pair, 1)
        if not candles:
            return "ERROR"
        
        candle = candles[0]
        if (direction == "CALL" and candle.close > candle.open) or \
           (direction == "PUT" and candle.close < candle.open):
            return "WIN"
        
        # Check second candle for MG WIN
        logger.info(f"Checking MG for {pair}...")
        await asyncio.sleep(60)
        
        candles = await self.get_candles(pair, 1)
        if not candles:
            return "LOSS"
        
        candle = candles[0]
        if (direction == "CALL" and candle.close > candle.open) or \
           (direction == "PUT" and candle.close < candle.open):
            return "MG WIN"
        
        return "LOSS"
    
    async def run(self):
        logger.info("Starting REDOX Bot v10.1")
        
        if not await self.init_quotex():
            logger.error("Failed to connect to Quotex")
            return
        
        while True:
            try:
                for pair in self.OTC_PAIRS:
                    logger.info(f"Analyzing {pair}...")
                    
                    candles = await self.get_candles(pair, 4)
                    if not candles:
                        logger.info(f"No data for {pair}")
                        continue
                    
                    result = self.analyze_reversal(candles)
                    if result:
                        direction, price = result
                        signal_msg = self.format_signal(pair, direction, price)
                        
                        if await self.send_message(signal_msg):
                            logger.info(f"Signal sent: {pair} {direction}")
                            
                            # Evaluate result
                            result_status = await self.evaluate_result(pair, direction)
                            result_msg = f"RESULT: {self.PAIR_NAMES.get(pair, pair)} -> {result_status}"
                            await self.send_message(result_msg)
                            
                            logger.info(f"Result: {pair} {direction} -> {result_status}")
                    else:
                        logger.info(f"No reversal pattern for {pair}")
                    
                    await asyncio.sleep(1)  # Small delay between pairs
                
                logger.info("Cycle complete, restarting...")
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(10)

async def main():
    bot = TelegramOTCBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        if bot.quotex_client:
            await bot.quotex_client.close()

if __name__ == "__main__":
    asyncio.run(main())