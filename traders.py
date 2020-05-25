"""
Basic traders adapted from:
https://github.com/davecliff/BristolStockExchange
"""


import asyncio
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
        self._securities = {ticker: Security(ticker, self._exchange_connection) for ticker in self._exchange_connection._securities}
        

    @abstractmethod
    async def run(self):
        pass

class GiveawayTrader(Trader):
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

        async def on_timeout(filled, unfilled):
            # Cancel the unfilled LMT orders
            cancellation_events = {order_id: asyncio.Event() for order_id in unfilled}
            unfilled_orders = list(unfilled.values())

            self._exchange_connection.cancel_orders(unfilled_orders, cancellation_events)
            await asyncio.gather(*[event.wait() for _, event in cancellation_events.items()])

            # Since we failed to fill via LMT orders create MKT orders for the remaining order specs
            # Don't check if these fill, we really don't care these are dumb liquidity providers / 
            # drive the market price path forward, not supposed to be a responsible trader
            
            await asyncio.gather(*[security.to_order(qty = order.qty, order_type = 'MKT', no_await=True).execute() for order in unfilled_orders])
    
        async def hedge(tender_order):
            inv_direction = Tender.get_inv_direction(tender_order)
            price_fn = Order.price_to_price_fn(tender_order.price)

            # Implements timeout to revert to market order if unable to fill limit within 30 seconds
            # This is purely to prevent market seizing up.
            hedging_order = inv_direction * security.to_order(qty = tender_order.qty, order_type = 'LMT', price_fn=price_fn, group_name='tender_%s' % security._ticker, timeout = 30, timeout_fn=on_timeout)

            await hedging_order.execute()

        def can_execute_tender(price, qty, direction):
            return True # Literally executes at whatever price the client gave them irresepctive of profitability.

        # The giveaway trader makes no profit, it simply tries to execute the tender at the clients demanded price
        tender = Tender(security, can_execute=can_execute_tender, group_name='tender_%s' % ticker).then(hedge)
        
        await tender.execute() 
