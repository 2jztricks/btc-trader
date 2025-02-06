import asyncio
import nest_asyncio
from app.core.database import Database  # Direct import
from app.core.bybit_client import BybitMarketData
from app.services.trade_service import TradeService
from app.strategies.lstm_strategy import LSTMStrategy
from app.utils.logger import configure_logger

configure_logger()

async def main():
    await Database.initialize()
    
    market_data = BybitMarketData()
    trade_service = TradeService()
    strategy = LSTMStrategy(trade_service)
    
    await asyncio.gather(
        market_data.run(),
        strategy.run()
    )

if __name__ == "__main__":
    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTrading bot stopped")