from frontend import Security, ExchangeConnection
import asyncio

EXCHANGE = ExchangeConnection()

RITC = Security('RITC', EXCHANGE)
BEAR = Security('BEAR', EXCHANGE)
BULL = Security('BULL', EXCHANGE)
USD = Security('USD', EXCHANGE)

UNDERLYINGS = BEAR + BULL
SPREAD = RITC - USD * UNDERLYINGS
SPREAD_USD_EXPSOURE = RITC * USD
HEDGED_SPREAD = SPREAD - SPREAD_USD_EXPSOURE

ORDER = HEDGED_SPREAD.to_order(qty = 100, order_type="MKT")
SIGNED_ORDER = SPREAD.inv_sign() * ORDER

THRESHOLD = SPREAD.trade_costs()

CONDITIONAL_ORDER = SIGNED_ORDER % (SPREAD.abs() > THRESHOLD)

UNWIND_CONDITIONAL_ORDER = CONDITIONAL_ORDER.unwind() % (SPREAD * CONDITIONAL_ORDER.sign() > THRESHOLD)
PAIRED_ORDER = CONDITIONAL_ORDER.on_complete(UNWIND_CONDITIONAL_ORDER)

loop = asyncio.get_event_loop()

strategies = asyncio.gather(PAIRED_ORDER.execute_on_interval())
core = asyncio.gather(EXCHANGE.connect_to_server())
trading_system = asyncio.gather(core, strategies)

loop.run_until_complete(trading_system)
