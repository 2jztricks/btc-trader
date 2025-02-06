import json
from pybit.unified_trading import WebSocket
import asyncio
from structlog import get_logger
from app.core.database import Database
from datetime import datetime, timezone

logger = get_logger(__name__)

class BybitMarketData:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.ws = None
        self.running = False
        self.loop = asyncio.get_event_loop()

    async def _connect_websocket(self):
        try:
            self.ws = WebSocket(
                testnet=False,
                channel_type="linear",
                api_key="your_api_key",
                api_secret="your_api_secret",
                trace_logging=False  # Disabled to remove debug noise
            )
            
            def handle_message(message):
                if 'data' in message and isinstance(message['data'], list):
                    for trade in message['data']:
                        if trade.get("S") in ["Buy", "Sell"] and trade.get("BT") == False:  # Only log bot-executed trades
                            asyncio.run_coroutine_threadsafe(
                                self._process_message(trade),
                                self.loop
                            )
            
            self.ws.trade_stream(
                symbol=self.symbol,
                callback=handle_message
            )
            logger.info("WebSocket connected successfully")
        except Exception as e:
            logger.error("WebSocket connection failed", error=str(e))
            raise

    async def _process_message(self, trade):
        try:
            price = float(trade.get('p', 0))
            features = json.dumps({
                'size': trade.get('v', 0),
                'side': trade.get('S', 'Unknown'),
                'trade_time': trade.get('T', 0)
            })
            await Database.execute('''
                INSERT INTO market_data (time, price, features)
                VALUES ($1, $2, $3)
            ''', datetime.now(timezone.utc), price, features)
            
            logger.info(f"TRADE EXECUTED: {trade.get('S')} @ {price}")
        except Exception as e:
            logger.error("Message processing failed", error=str(e))

    async def run(self):
        self.running = True
        while self.running:
            try:
                if not self.ws:
                    await self._connect_websocket()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                self.ws = None
                await asyncio.sleep(5)

    async def stop(self):
        self.running = False
        if self.ws:
            self.ws.exit()
        logger.info("WebSocket stopped")
