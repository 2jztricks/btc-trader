import asyncpg
from structlog import get_logger
from app.core.config import Config

logger = get_logger(__name__)

class Database:
    _pool = None

    @classmethod
    async def get_pool(cls):
        if not cls._pool:
            cls._pool = await asyncpg.create_pool(
                **Config.DB_CONFIG,
                min_size=5,
                max_size=20
            )
        return cls._pool

    @classmethod
    async def execute(cls, query, *args):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetch(cls, query, *args):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def initialize(cls):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb;')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS market_data (
                    time TIMESTAMPTZ NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION NOT NULL,
                    rsi DOUBLE PRECISION NOT NULL,
                    macd DOUBLE PRECISION NOT NULL
                );
            ''')
            await conn.execute("SELECT create_hypertable('market_data', 'time');")
            logger.info("Database initialized")

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            logger.info("Database connection closed")