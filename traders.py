"""
Basic traders adapted from:
https://github.com/davecliff/BristolStockExchange
"""


import asyncio
from time import time
import json
from random import betavariate
from math import floor, log10
from frontend import ExchangeConnection, Security, Tender, Order
from abc import ABC, abstractmethod

class Trader(ABC):
    # TODO: For now we will run in a single thread with one instance of each trader 
    # however we will soon want to scale this up to many asyncio trader clones per core Process

    def __init__(self, enable_app=False, name='not_implemented'):
        ABC.__init__(self)
        self._connection_established = asyncio.Event()
        self._exchange_connection = ExchangeConnection(enable_app=enable_app, name=name, setup_event = self._connection_established)
        self._securities = {}

    async def connect(self): 
        """
        Must be called to start the bot!
        """
        await asyncio.gather(self._exchange_connection.connect_to_server(), self.on_connection())

    async def on_connection(self):
        await self._connection_established.wait()

        self.init_secuirties()

        await self.run()

    def init_secuirties(self):
        # Since the exchange connection is unique to the trader...
        self._securities = self._exchange_connection._security_objects

    @abstractmethod
    async def run(self):
        pass

class LiquidityTaker(Trader):
    """
    Its only role is to absorb some of the liquidity provided by Giveaway Traders.
    Remember the role of the giveaway trader is simply to convey clients opinions on price
    movements into the market. By hoovering up these limit orders we enable transactions to occur
    and to bake those movements into the market.
    """
    def __init__(self, backend_config_dir='./configs/backend_config.json'):
        super().__init__()
        
        with open(backend_config_dir) as config_file:
             self._backend_config = json.load(config_file)

        self._case_name = self._backend_config['exchanges']['active_case']
        self._secuirties_config = self._backend_config['exchanges'][self._case_name]['securities']

    async def run(self):
        await asyncio.gather(*[self.absorb_market_liquidity(ticker) for ticker in self._securities])

    @staticmethod
    def round_to_2_sf(x):
        return round(x, 1-int(floor(log10(abs(x)))))

    async def absorb_market_liquidity(self, ticker):
        institutional_orders = self._secuirties_config[ticker]['market_dynamics']['institutional_orders']
        security = self._securities[ticker]

        if institutional_orders['enabled']:
            expected_tender_qty = institutional_orders['expected_tender_qty']

            while True:
                qty1 = self.round_to_2_sf(expected_tender_qty * 3/2 * betavariate(3, 1.5))
                qty2 = self.round_to_2_sf(expected_tender_qty * 3/2 * betavariate(3, 1.5))
                mkt_order_1 = security.to_order(qty = qty1, order_type = 'MKT', group_name='liquidity_taker_%s' % security._ticker, await_fills=False) # Again really don't care when its executed 
                mkt_order_2 = security.to_order(qty = qty2, order_type = 'MKT', group_name='liquidity_taker_%s' % security._ticker, await_fills=False) # Again really don't care when its executed

                # Execute a market order on each side
                await mkt_order_1.execute()
                await (-1 * mkt_order_2).execute() 
                await asyncio.sleep(3) # Send out an order every second


class GiveawayTrader(Trader):
    """
    A simple trader who accepts tenders from clients and executes them at the clients limit price
    hence a 'giveaway' trader who earns no money. Note the trader will however dump the position at MKT
    if it holds its position longer than a predefined timeout
    """


    def __init__(self):
        super().__init__()

    async def run(self):
        # Waits for tenders (and executes where appropriate on all securities)
        await asyncio.gather(*[self.execute_tenders_on_security(ticker) for ticker in self._securities])

    async def execute_tenders_on_security(self, ticker):
        """
        :param security: A security object assigned to the trader
        """
        security = self._securities[ticker]
        self._outstanding_hedges = 1 # Avoids divide by zero
        self._completed_hedges = 1

        async def on_timeout(filled, unfilled):
            # Cancel the unfilled LMT orders
            cancellation_events = {order_id: asyncio.Event() for order_id in unfilled}
            unfilled_orders = list(unfilled.values())

            self._exchange_connection.cancel_orders(unfilled_orders, cancellation_events)
            await asyncio.gather(*[event.wait() for _, event in cancellation_events.items()])

            # Since we failed to fill via LMT orders create MKT orders for the remaining order specs
            # Don't check if these fill, we really don't care these are dumb liquidity providers / 
            # drive the market price path forward, not supposed to be a responsible trader
            
            await asyncio.gather(*[security.to_order(qty = order.qty, order_type = 'MKT', await_fills=False).execute() for order in unfilled_orders])
    
        async def hedge(tender_order):
            inv_direction = Tender.get_inv_direction(tender_order)
            price_fn = Order.price_to_price_fn(tender_order.price)

            # Implements timeout to revert to market order if unable to fill limit within 30 seconds
            # This is purely to prevent market seizing up.
            hedging_order = inv_direction * security.to_order(qty = tender_order.qty, order_type = 'LMT', price_fn=price_fn, group_name='tender_%s' % security._ticker, timeout = 3, timeout_fn=on_timeout)
            
            await hedging_order.execute()

        def can_execute_tender(price, qty, direction):
            return True # Literally executes at whatever price the client gave them irresepctive of profitability.

        # The giveaway trader makes no profit, it simply tries to execute the tender at the clients demanded price
        tender = Tender(security, can_execute=can_execute_tender, group_name='tender_%s' % ticker).then(hedge)
        
        await tender.execute() 
