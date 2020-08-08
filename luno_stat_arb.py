from traders import StatArbTrader
import asyncio

trader = StatArbTrader()
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(trader.connect()))