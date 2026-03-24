import asyncio
from aiomql import MetaTrader
from aiomql import Config
from stratergies.sontinh_strg import SonTinhStrategy
from aiomql import Bot, ForexSymbol
from utils.logger import logger
from aiomql import Session, Sessions, ForexSymbol, Chaos
from config.config import load_config_from_json

load_config = load_config_from_json()
config = Config(login=load_config.get('login'),
                password=load_config.get('password'),
                server=load_config.get('server'),
                path=load_config.get('path', ''))


async def main():
    logger.info("Start BOT")
    bot = Bot()
    syms = ["XAUUSD"]
    strategies = [SonTinhStrategy()
                  for sym in syms]
    bot.add_strategies(strategies=strategies)
    await bot.start()


asyncio.run(main())
