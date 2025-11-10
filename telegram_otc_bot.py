#!/usr/bin/env python3
"""
Telegram OTC Bot for PyQuotex - REDOX v10.1
Monitors OTC pairs and sends trading signals via Telegram
"""

import os
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from telegram import Bot
from dotenv import load_dotenv

# Import from existing PyQuotex API
from pyquotex.stable_api import Quotex

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CandleData:
    """Candle data structure"""
    open: float
    high: float
    low: float
    close: float
    timestamp: int

class TelegramOTCBot:
    """Main bot class for OTC trading signals"""
    
    # OTC pairs to monitor
    OTC_PAIRS = [
        "AUDNZD_otc", "AXP_otc", "BA_otc", "BRLUSD_otc", "BTCUSD_otc", 
        "CADCHF_otc", "EURNZD_otc", "FB_otc", "NZDCAD_otc", "NZDCHF_otc", 
        "NZDJPY_otc", "PFE_otc", "UKBrent_otc", "USCrude_otc", "USDARS_otc", 
        "USDBDT_otc", "USDCOP_otc", "USDDZD_otc", "USDEGP_otc", "USDIDR_otc", 
        "USDINR_otc", "USDJPY_otc", "USDMXN_otc", "USDNGN_otc", "USDPHP_otc", 
        "USDPKR_otc", "USDTRY_otc", "USDZAR_otc", "XAGUSD_otc", "XAUUSD_otc"
    ]
    
    # Readable names mapping
    PAIR_NAMES = {
        "AUDNZD_otc": "AUD/NZD (OTC)",
        "AXP_otc": "American Express (OTC)",
        "BA_otc": "Boeing Company (OTC)",
        "BRLUSD_otc": "USD/BRL (OTC)",
        "BTCUSD_otc": "Bitcoin (OTC)",
        "CADCHF_otc": "CAD/CHF (OTC)",
        "EURNZD_otc": "EUR/NZD (OTC)",
        "FB_otc": "Facebook Inc (OTC)",
        "NZDCAD_otc": "NZD/CAD (OTC)",
        "NZDCHF_otc": "NZD/CHF (OTC)",
        "NZDJPY_otc": "NZD/JPY (OTC)",
        "PFE_otc": "Pfizer Inc (OTC)",
        "UKBrent_otc": "UK Brent (OTC)",
        "USCrude_otc": "US Crude (OTC)",
        "USDARS_otc": "USD/ARS (OTC)",
        "USDBDT_otc": "USD/BDT (OTC)",
        "USDCOP_otc": "USD/COP (OTC)",
        "USDDZD_otc": "USD/DZD (OTC)",
        "USDEGP_otc": "USD/EGP (OTC)",
        "USDIDR_otc": "USD/IDR (OTC)",
        "USDINR_otc": "USD/INR (OTC)",
        "USDJPY_otc": "USD/JPY (OTC)",
        "USDMXN_otc": "USD/MXN (OTC)",
        "USDNGN_otc": "USD/NGN (OTC)",
        "USDPHP_otc": "USD/PHP (OTC)",
        "USDPKR_otc": "USD/PKR (OTC)",
        "USDTRY_otc": "USD/TRY (OTC)",
        "USDZAR_otc": "USD/ZAR (OTC)",
        "XAGUSD_otc": "Silver (OTC)",
        "XAUUSD_otc": "Gold (OTC)"
    }
    
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.bot: Optional[Bot] = None
        self.quotex_client: Optional[Quotex] = None
        self.last_signal_time = 0
        self.min_volatility_threshold = 0.00001  # Lower threshold for more pairs
        self.win_count = 0
        self.loss_count = 0
        
        # Martingale state variables
        self.base_stake = 1.0  # Initial stake amount
        self.current_stake = 1.0  # Current trade stake
        self.martingale_factor = 2.0  # Multiplier for MTG trades
        self.in_martingale_sequence = False  # Track if in MTG sequence
        
        # Initialize Telegram bot if token provided
        if self.telegram_token:
            self.bot = Bot(token=self.telegram_token)
        else:
            logger.warning("No Telegram token provided - signals will be logged only")
    
    async def init_quotex(self) -> bool:
        """Initialize Quotex connection with retry logic"""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.quotex_client = Quotex()
                success, reason = await self.quotex_client.connect()
                
                if success:
                    logger.info("Successfully connected to Quotex")
                    return True
                else:
                    logger.error(f"Failed to connect to Quotex: {reason}")
                    
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
        
        return False
    
    async def get_candles_for_pair(self, pair: str, limit: int = 4) -> Optional[List[CandleData]]:
        """Fetch recent candles for a pair"""
        try:
            if not self.quotex_client:
                return None
            
            # Fetch candles using existing API (60 seconds = 1 minute)
            end_time = time.time()
            offset = limit * 60  # 60 seconds per candle
            
            candles_raw = await self.quotex_client.get_candles(
                asset=pair,
                end_from_time=end_time,
                offset=offset,
                period=60  # 1 minute candles
            )
            
            if not candles_raw:
                return None
            
            # Convert to CandleData objects
            candles = []
            for candle in candles_raw[-limit:]:  # Get last N candles
                candles.append(CandleData(
                    open=float(candle.get('open', 0)),
                    high=float(candle.get('high', 0)),
                    low=float(candle.get('low', 0)),
                    close=float(candle.get('close', 0)),
                    timestamp=int(candle.get('time', 0))
                ))
            
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching candles for {pair}: {e}")
            return None
    
    def score_pair(self, candles: List[CandleData]) -> Tuple[float, str, float]:
        """
        New reversal logic: if last 4 candles are same direction, predict reversal
        Returns: (direction_score, direction, last_price)
        """
        if len(candles) < 4:
            return 0.0, "NONE", 0.0
        
        # Check last 4 candles direction
        directions = []
        for candle in candles:
            if candle.close > candle.open:
                directions.append("CALL")
            elif candle.close < candle.open:
                directions.append("PUT")
            else:
                directions.append("NEUTRAL")
        
        # Check if last 4 candles are same direction
        if len(set(directions)) == 1 and directions[0] != "NEUTRAL":
            # Reversal signal - opposite of last 4 candles
            direction = "PUT" if directions[0] == "CALL" else "CALL"
            # High score for reversal pattern
            direction_score = 100.0
        else:
            # Regular momentum logic
            candle_changes = [c.close - c.open for c in candles]
            momentum = (0.6 * candle_changes[-1]) + (0.4 * candle_changes[-2])
            volatility = sum(c.high - c.low for c in candles) / len(candles)
            direction_score = abs(momentum) * volatility
            direction = "CALL" if momentum > 0 else "PUT"
        
        return direction_score, direction, candles[-1].close
    
    async def analyze_single_pair(self, pair: str) -> Optional[Tuple[str, str, float, float]]:
        """
        Analyze a single pair for signal
        Returns: (pair, direction, score, price) or None
        """
        candles = await self.get_candles_for_pair(pair, 4)
        if not candles:
            return None
        
        score, direction, price = self.score_pair(candles)
        
        # Filter out low volatility pairs
        volatility = sum(c.high - c.low for c in candles) / len(candles)
        if volatility < self.min_volatility_threshold:
            return None
        
        return (pair, direction, score, price)
    
    async def evaluate_signal_result(self, pair: str, direction: str):
        """
        Enhanced M1 Martingale Sequence Logic
        Phase 1: Initial Trade (T) - Entry at T, Expiry at T+60s
        Phase 2: MTG Trade (T+1) - Entry at T+60s, Expiry at T+120s (if Phase 1 loses)
        """
        # Reset Martingale state for new sequence
        self.current_stake = self.base_stake
        self.in_martingale_sequence = True
        
        # PHASE 1: Initial Trade (Candle T)
        initial_entry_time = datetime.now()
        initial_timestamp = int(time.time())
        
        logger.info(f"=== PHASE 1: Initial Trade ===")
        logger.info(f"Entry: {initial_entry_time.strftime('%H:%M:%S')} | {pair} {direction} | Stake: {self.current_stake}")
        
        # Wait for initial trade candle to close (T + 60s)
        await asyncio.sleep(65)  # 60s + 5s buffer
        
        # Get initial trade result
        initial_result = await self.check_trade_result(pair, direction, initial_timestamp)
        
        if initial_result == "WIN":
            # Phase 1 WIN - Sequence complete
            result = "WIN"
            self.win_count += 1
            self.in_martingale_sequence = False
            self.current_stake = self.base_stake
            logger.info(f"SEQUENCE COMPLETE: Initial WIN")
        else:
            # Phase 1 LOSS - Proceed to Martingale
            logger.info(f"=== PHASE 2: Martingale Trade ===")
            
            # Update stake for MTG trade
            self.current_stake = self.base_stake * self.martingale_factor
            mtg_entry_time = datetime.now()
            mtg_timestamp = int(time.time())
            
            logger.info(f"MTG Entry: {mtg_entry_time.strftime('%H:%M:%S')} | {pair} {direction} | Stake: {self.current_stake}")
            
            # Send MTG signal notification
            mtg_message = self.format_mtg_message(pair, direction, self.current_stake)
            await self.send_telegram(mtg_message)
            
            # Wait for MTG trade candle to close (T + 120s total)
            await asyncio.sleep(65)  # 60s + 5s buffer
            
            # Get MTG trade result
            mtg_result = await self.check_trade_result(pair, direction, mtg_timestamp)
            
            if mtg_result == "WIN":
                # MTG WIN - Sequence complete
                result = "MTG WIN"
                self.win_count += 1
                logger.info(f"SEQUENCE COMPLETE: MTG WIN")
            else:
                # MTG LOSS - Sequence complete
                result = "LOSS"
                self.loss_count += 1
                logger.info(f"SEQUENCE COMPLETE: TOTAL LOSS")
            
            # Reset Martingale state
            self.in_martingale_sequence = False
            self.current_stake = self.base_stake
        
        # Send final result
        result_message = self.format_result_message(result)
        await self.send_telegram(result_message)
        
        log_entry = f"{pair} {direction} → {result}"
        self.log_signal(log_entry)
    
    async def check_trade_result(self, pair: str, direction: str, entry_timestamp: int) -> str:
        """
        Check M1 trade result for specific candle
        Returns: "WIN" or "LOSS"
        """
        candles = await self.get_candles_for_pair(pair, 2)
        if not candles:
            logger.error(f"Failed to get candles for {pair}")
            return "LOSS"
        
        # Find correct candle by timestamp
        trade_candle = None
        for candle in candles:
            if abs(candle.timestamp - entry_timestamp) <= 60:
                trade_candle = candle
                break
        
        if not trade_candle:
            trade_candle = candles[-1]
        
        entry_price = trade_candle.open
        close_price = trade_candle.close
        
        logger.info(f"Candle: Open={entry_price:.5f}, Close={close_price:.5f}")
        
        # M1 Binary Options Win Logic
        if direction == "CALL":
            is_win = close_price > entry_price
        else:  # PUT
            is_win = close_price < entry_price
        
        return "WIN" if is_win else "LOSS"
    
    def format_mtg_message(self, pair: str, direction: str, stake: float) -> str:
        """
        Format MTG signal message
        """
        readable_name = self.PAIR_NAMES.get(pair, pair).replace(" (OTC)", "-OTC")
        next_minute = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
        time_str = next_minute.strftime("%H:%M")
        direction_emoji = "🔴" if direction == "PUT" else "🟢"
        
        return f"""╭━━━━━━━━━━・━━━━━━━━━━╮
🔥 MTG TRADE -» {readable_name}
🕓 TIMETABLE -» {time_str}
⏳ EXPIRATION-» M1
{direction_emoji} DIRECTION -» {direction}
💰 STAKE     -» {stake:.1f}x
╰━━━━━━━━━━・━━━━━━━━━━╯"""
    
    def format_message(self, pair: str, direction: str, price: float) -> str:
        """Format the Telegram message with custom styling"""
        readable_name = self.PAIR_NAMES.get(pair, pair).replace(" (OTC)", "-OTC")
        next_minute = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
        time_str = next_minute.strftime("%H:%M")
        
        # Direction emoji
        direction_emoji = "🔴" if direction == "PUT" else "🟢"
        
        message = f"""╭━━━━━━━━━━・━━━━━━━━━━╮
🐲 OPEN PAIR -» {readable_name}
🕓 TIMETABLE -» {time_str}
⏳ EXPIRATION-» M1
{direction_emoji} DIRECTION -» {direction}
📶 PRICE     -» {price:.4f}
╰━━━━━━━━━━・━━━━━━━━━━╯"""
        
        return message
    
    def format_result_message(self, result: str) -> str:
        """Format the result message with custom styling"""
        if result == "WIN":
            message = f"""╭━━━━━━━━━━・━━━━━━━━━━╮
✅✅  SURESHOT  ✅✅

WIN :- {self.win_count:02d} OTM :- {self.loss_count:02d}
╰━━━━━━━━━━・━━━━━━━━━━╯"""
        elif result == "MTG WIN":
            message = f"""╭━━━━━━━━━━・━━━━━━━━━━╮
✅✅  MTG WIN  ✅✅

WIN :- {self.win_count:02d} OTM :- {self.loss_count:02d}
╰━━━━━━━━━━・━━━━━━━━━━╯"""
        else:  # LOSS
            message = f"""╭━━━━━━━━━━・━━━━━━━━━━╮
❌❌  LOSS  ❌❌

WIN :- {self.win_count:02d} OTM :- {self.loss_count:02d}
╰━━━━━━━━━━・━━━━━━━━━━╯"""
        
        return message
    
    async def test_telegram(self) -> bool:
        """Test Telegram bot connection"""
        if not self.bot or not self.chat_id:
            logger.warning("Telegram not configured")
            return False
        
        try:
            test_msg = "🤖 REDOX Bot Test - Connection OK"
            await self.bot.send_message(chat_id=self.chat_id, text=test_msg)
            logger.info("Telegram test message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            return False
    
    async def send_telegram(self, message: str) -> bool:
        """Send message via Telegram"""
        if not self.bot or not self.chat_id:
            # Log to console and file if no Telegram config
            print(f"\n{message}\n")
            self.log_signal(message)
            return True
        
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
            logger.info("Signal sent via Telegram")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            # Fallback to console/file logging
            print(f"\n{message}\n")
            self.log_signal(message)
            return False
    
    def log_signal(self, message: str):
        """Log signal to file"""
        try:
            with open("signals.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} - {message}\n\n")
        except Exception as e:
            logger.error(f"Failed to log signal: {e}")
    
    def get_next_candle_time(self) -> datetime:
        """Get the next minute boundary"""
        now = datetime.now()
        return now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    
    def get_signal_send_time(self) -> datetime:
        """Get time to send signal (30 seconds before next candle)"""
        next_candle = self.get_next_candle_time()
        return next_candle - timedelta(seconds=30)
    
    async def reconnect_if_needed(self):
        """Reconnect to Quotex if connection is lost"""
        try:
            if not self.quotex_client or not await self.quotex_client.check_connect():
                logger.warning("Connection lost, attempting to reconnect...")
                if await self.init_quotex():
                    logger.info("Reconnection successful")
                else:
                    logger.error("Reconnection failed")
        except Exception as e:
            logger.error(f"Error during reconnection check: {e}")
    
    async def run(self):
        """Main bot loop - sequential analysis of all pairs"""
        logger.info("Starting Telegram OTC Bot - REDOX v10.1 (Sequential Mode)")
        
        # Test Telegram connection
        if self.telegram_token:
            await self.test_telegram()
        
        # Initialize Quotex connection
        if not await self.init_quotex():
            logger.error("Failed to initialize Quotex connection")
            return
        
        logger.info(f"Sequential monitoring of {len(self.OTC_PAIRS)} OTC pairs")
        
        while True:
            try:
                # Check connection health
                await self.reconnect_if_needed()
                
                # Loop through all pairs sequentially
                for pair in self.OTC_PAIRS:
                    try:
                        logger.info(f"Analyzing pair: {pair}")
                        
                        # Analyze single pair
                        result = await self.analyze_single_pair(pair)
                        
                        if result:
                            pair_name, direction, score, price = result
                            message = self.format_message(pair_name, direction, price)
                            
                            # Send signal
                            if await self.send_telegram(message):
                                logger.info(f"Signal sent for {pair} - {direction} at {price}")
                                
                                # Log signal
                                signal_log = f"{pair} {direction} signal at {price}"
                                self.log_signal(signal_log)
                                
                                # Evaluate result (this will take ~2 minutes)
                                await self.evaluate_signal_result(pair, direction)
                            else:
                                logger.error(f"Failed to send signal for {pair}")
                        else:
                            logger.info(f"No signal generated for {pair} (low volatility or no data)")
                        
                        # Small delay between pairs
                        await asyncio.sleep(2)
                        
                    except Exception as e:
                        logger.error(f"Error processing pair {pair}: {e}")
                        continue
                
                # Completed all pairs, small delay before next cycle
                logger.info("Completed analysis of all pairs. Starting next cycle...")
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying

async def main():
    """Main entry point"""
    bot = TelegramOTCBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        if bot.quotex_client:
            await bot.quotex_client.close()

if __name__ == "__main__":
    asyncio.run(main())