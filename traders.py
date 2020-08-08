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
from pricing import improve_on_best_quote

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



class MultiExchangeTrader(ABC):
    # TODO: For now we will run in a single thread with one instance of each trader 
    # however we will soon want to scale this up to many asyncio trader clones per core Process

    def __init__(self, enable_app=False, name='not_implemented', exchange_names = ['BITSTAMP', 'LUNO']):
        ABC.__init__(self)
        
        self._connection_established = {name: asyncio.Event() for name in exchange_names}
        self._exchange_connections = {}
        self._securities = {}

        for idx, exchange_name in enumerate(exchange_names):
            conn = ExchangeConnection(enable_app=False, name=exchange_name, uri=self.get_ws_uri(exchange_name.lower()), setup_event = self._connection_established[idx])
            self._exchange_connections[exchange_name] = conn       
    
    def get_ws_uri(self, exchange_name):
        with open('./configs/backend_config.json') as config_file:
            config = json.load(config_file)
            websocket_details = config['exchanges'][exchange_name]['websocket']
            uri = 'ws://' + str(websocket_details['ip']) + ':' + str(websocket_details['port']) + '/trader'
            return uri

    async def connect(self): 
        """
        Must be called to start the bot!
        """
        connect =  asyncio.gather(*[conn.connect_to_server() for name, conn in self._exchange_connections.items()])
        wait_for = asyncio.gather(*[self.on_connection(name) for name, conn in self._exchange_connections.items()])
        await asyncio.gather(connect, wait_for)

    async def on_connection(self, exchange_name):
        await self._connection_established[exchange_name].wait()

        self.init_secuirties(exchange_name)

        await self.run()

    def init_secuirties(self, exchange_name):
        # Since the exchange connection is unique to the trader...
        self._securities[exchange_name] = self._exchange_connections[exchange_name]._security_objects

    @abstractmethod
    async def run(self):
        pass

class StatArbTrader(MultiExchangeTrader):

    def __init__(self, LAhandle = 5, LBhandle = 5, qty_to_trade = 1):
        super().__init__(enable_app=True)
        self.LAhandle = LAhandle
        self.LBhandle = LBhandle
        self.qty_to_trade = qty_to_trade

    async def run(self):
        print("Started trading --------")
    
        def can_enter_arbitrage():
            l_ask = L_BTCEUR.evaluate(-1) 
            b_bid = B_BTCEUR.evaluate(1) 
            open_signal = l_ask - b_bid < -1 * self.LAhandle

            return open_signal
        
        def can_exit_arbitrage():
            l_bid = L_BTCEUR.evaluate(1) 
            b_ask = B_BTCEUR.evaluate(-1) 
            close_signal = l_bid - b_ask > self.LBhandle

            return close_signal

        def cross_spread(direction, evaluate):
            # Best Ask - Best Bid
            spread = evaluate(-1) - evaluate(1)
            spread_plus = spread + 0.01
            # Buy
            marketable_buy_price = evaluate(1) + spread_plus
            marketable_sell_price = evaluate(-1) - (spread + 0.01)
            is_buying = direction == 1

            return marketable_buy_price if is_buying else marketable_sell_price

        B_BTCEUR =  self._securities['BITSTAMP']['btceur']
        L_BTCEUR =  self._securities['LUNO']['XBTEUR']

        while True:
            await asyncio.sleep(0.5)
            
            # Wait for the spread to pass some threshold 
            # Then place approrpiate marketable limit orders
            OPEN_LUNO_POSITION = L_BTCEUR.to_order(
                qty=self.qty_to_trade,
                can_execute=can_enter_arbitrage,
                order_type='LMT',
                price_fn=cross_spread
            )

            OPEN_BITSTAMP_POSITION = -1 * (B_BTCEUR.to_order(
                qty=self.qty_to_trade, 
                can_execute=can_enter_arbitrage,
                order_type='LMT',
                price_fn=cross_spread
            ))

            # Define how we are going to unwind the trade
            # with appropriate exit conditions
            CLOSE_LUNO_POSITION = OPEN_LUNO_POSITION.unwind()
            CLOSE_LUNO_POSITION.can_execute = can_exit_arbitrage
            
            CLOSE_BITSTAMP_POSITION = OPEN_BITSTAMP_POSITION.unwind()
            CLOSE_BITSTAMP_POSITION.can_execute = can_exit_arbitrage

            # Define the forward and reverse sequences for both arb directions 
            # (-ve to +ve spread and +ve to -ve spread)
            LUNO_TRADE_SEQUENCE_FWD = OPEN_LUNO_POSITION.then(CLOSE_LUNO_POSITION)
            BITSTAMP_TRADE_SEQUENCE_FWD = OPEN_BITSTAMP_POSITION.then(CLOSE_BITSTAMP_POSITION)

            LUNO_TRADE_SEQUENCE_BKWD = CLOSE_LUNO_POSITION.then(OPEN_LUNO_POSITION)
            BITSTAMP_TRADE_SEQUENCE_BKWD = CLOSE_BITSTAMP_POSITION.then(OPEN_BITSTAMP_POSITION)
            
            LUNO_SEQ = LUNO_TRADE_SEQUENCE_FWD.then(LUNO_TRADE_SEQUENCE_BKWD)
            BITSTAMP_SEQ = BITSTAMP_TRADE_SEQUENCE_FWD.then(BITSTAMP_TRADE_SEQUENCE_BKWD)

            # Wait for success or failure of the trade
            await asyncio.gather(*[LUNO_SEQ.execute(), BITSTAMP_SEQ.execute()])



    