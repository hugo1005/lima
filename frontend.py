import numpy as np
import asyncio
import websockets
import operator
import json
import pathlib
import ssl
import re

from collections import namedtuple
from threading import Thread
from time import sleep, time
from math import floor
import warnings

from shared import LOB, OrderSpec, ExchangeOrder, Transaction, to_named_tuple, CompositionMeta, ComplexEvent, OrderKey, TickerPnL, TraderRisk, TenderOrder, RiskLimits
from shared import to_named_tuple, cast_named_tuple_to_dict, named_tuple_to_dict

class Security:
    def __init__(self, ticker, exchange_connection, evaluate = None, trade_costs = None, composition = None, rebate = None, tender_rejection_window = 0.5):
        self._ticker = ticker # Purely a naming convention
        self._exchange = exchange_connection # Purely for information purposes

        # Potentially there may be some compute time required
        # to evaluate a tender
        # TODO in theory we could run a test to estimate
        # based on server ping and function evaluation time
        # so that might be more optimal than an arbitrary threshold
        self._tender_rejection_window = tender_rejection_window
        
        # Computes the trade cost of the underlying 
        # Or to the costs of the collective underlyings
        if type(trade_costs) == type(None):
            base_trade_cost = self._exchange.get_trade_cost(self._ticker)

            def trade_costs_base():
                return base_trade_cost

            self.trade_costs = trade_costs_base
        else:
            self.trade_costs = trade_costs

        # Computes the rebate from limit order on the underlying 
        # Or to the rebate of the collective underlyings
        if type(rebate) == type(None):
            base_rebate = self._exchange.get_rebate(self._ticker)

            def reabte_base():
                return base_rebate

            self.rebate = reabte_base
        else:
            self.rebate = rebate

        # Computes the current price of the underlying 
        # Or to the price of the collective underlyings
        # As specified by the security equation
        if type(evaluate) == type(None):
            def evaluate_base(sign = 1):
                lob = self._exchange.get_LOB(ticker)
                midprice = (lob.best_bid + lob.best_ask) / 2
                midprice = round(midprice, self.resolution(lob.best_bid))
                
                price = {-1: float(lob.best_ask), 0: float(midprice), 1: float(lob.best_bid)}
                return price[sign]

            self.evaluate = evaluate_base
        else:
            self.evaluate = evaluate

        # Computes the ratio / mix of underlying assets
        # for the composed security, this is evaluated dynamically
        # The sign should be either 1 = BUY, -1 = SELL, this will infer the correct price
        if type(composition) == type(None):
            def composition_base(multiplier = 1): # a generalisation of sign
                sign = -1 if multiplier < 0 else 1
                return {ticker: CompositionMeta(multiplier, self.evaluate(sign))}

            self.composition = composition_base
        else:
            self.composition = composition
    
    @staticmethod
    def resolution(value):
        return len(str(value).split('.'))
    
    def __add__(self, other):
        def evaluate(sign = 1):
            a = self.evaluate(sign)
            b = other.evaluate(sign)
            
            return round(a + b, self.resolution(b))
        
        def trade_costs():
            a = self.trade_costs()
            b = other.trade_costs()

            return a + b

        def rebate():
            a = self.rebate()
            b = other.rebate()

            return a + b
        
        def composition(sign = 1):
            new_composition = {**self.composition(sign), **other.composition(sign)}

            return new_composition

        new_ticker = "(%s)+(%s)" % (self._ticker, other._ticker)

        return Security(new_ticker, self._exchange, evaluate = evaluate, trade_costs = trade_costs, composition=composition, rebate=rebate, tender_rejection_window = self._tender_rejection_window)
        
    def __sub__(self, other):
        def evaluate(sign = 1):
            # We wish to reflect the true price of the asset rather than simply the midprice
            # Hence we take the bid ask spread into account as well as computing the price difference
            a = self.evaluate(sign)
            b = other.evaluate(-1 * sign)
            
            return round(a - b, self.resolution(b))
        
        def trade_costs():
            a = self.trade_costs()
            b = other.trade_costs()

            return a + b

        def composition(sign = 1):
            new_composition = {**self.composition(sign), **other.composition(-1 * sign)}
            
            return new_composition

        def rebate():
            a = self.rebate()
            b = other.rebate()

            return a + b

        new_ticker = "(%s)-(%s)" % (self._ticker, other._ticker)

        return Security(new_ticker, self._exchange, evaluate = evaluate, trade_costs = trade_costs, composition=composition, rebate=rebate,tender_rejection_window = self._tender_rejection_window)
    
    def __mul__(self, other):
        if type(other) == float or type(other) == int:
            return self.__rmul__(other) # Deals with scalar multiplication

        def evaluate(sign = 1):
            a = self.evaluate(0) # Always the mid price for something we are using only to scale
            x = other.evaluate(sign)
            
            return round(a * x, self.resolution(x))
        
        def trade_costs():
            a = self.evaluate(0)
            b = other.trade_costs()

            return a * b
        
        def rebate():
            a = self.evaluate(0)
            b = other.rebate()

            return a * b

        def composition(sign = 1):
            multiplier = self.evaluate(0)
            new_composition = other.composition(multiplier * sign) # This is an abuse of notation but it works slickly

            return new_composition

        new_ticker = "(%s)*(%s)" % (self._ticker, other._ticker)

        return Security(new_ticker, self._exchange, evaluate = evaluate, trade_costs = trade_costs, composition=composition, rebate = rebate, tender_rejection_window = self._tender_rejection_window)

    def __rmul__(self, other):
        # This method is used for pre multiplying by a scalar (not a security)
        if type(other) != float and type(other) != int:
            raise ValueError('Can only premultiply a security by a number!')

        def evaluate(sign = 1):
            a = other
            x = self.evaluate(sign)
            
            return round(a * x, self.resolution(x))
        
        def trade_costs():
            a = other
            b = self.trade_costs()

            return a * b

        def rebate():
            a = other
            b = self.rebate()

            return a * b

        def composition(sign = 1):
            multiplier = other
            new_composition = self.composition(multiplier * sign) # This is an abuse of notation but its slick
            
            return new_composition

        new_ticker = "(%s)*(%s)" % (other, self._ticker)

        return Security(new_ticker, self._exchange, evaluate = evaluate, trade_costs = trade_costs, composition=composition, rebate = rebate,tender_rejection_window = self._tender_rejection_window)      

    def __lt__(self, other):
        return self.rich_comparison(self, other, operator.lt)

    def __gt__(self, other):
        return self.rich_comparison(self, other, operator.gt)

    def __ge__(self, other):
        return self.rich_comparison(self, other, operator.ge)

    def __le__(self, other):
        return self.rich_comparison(self, other, operator.le)

    def __eq__(self, other):
        return self.rich_comparison(self, other, operator.eq)

    def __neq__(self, other):
        return self.rich_comparison(self, other, operator.ne)

    @staticmethod
    def rich_comparison(x,y,op):
        if type(y) != float and type(y) != int and type(y) != Security:
            raise ValueError('Can only make comparison with a number or security') 

        def comparison():
            if type(y) == Security:
                return op(x.evaluate(0), y.evaluate(0))
            else:
                return op(x.evaluate(0), y)

        return comparison

    def assign_trader(self, trader):
        """
        A special function to assign the security to a specific trader
        so that the order may be executed on there account.
        :param trader: of type ExchangeConnection
        :param Security: A new instance of the security with the correct exchange connection
        """
        return Security(self._ticker, trader, evaluate = self.evaluate, trade_costs = self.trade_costs, composition=self.composition, rebate = self.rebate, tender_rejection_window = self._tender_rejection_window)

    def to_order(self, **kwargs):
        """
        Converts a security to an order object when can be executed
        :param qty: The amount to buy / sell of security
        :param qty_fn: A generalisation of qty which is a function which dynamically returns qty when called
         Note that qty will be implicityly converted to a qty_fn. Either qty or qty_fn must be specified
        :param order_type: One of MKT, LMT, TENDER
        :param direction: 1 for Buy, -1 for Sell
        :param can_execute: A boolean valued function, which it is preferred to be set using % operator. Although
        internally the condition passed to % will be implemented by passing the argument
        :param on_complete: A function that returns another order.execute (Should never be required explictly)
        :param price: A function which accepts (direction ~ int, evaluate ~ Security.evaluate) and returns a lmt price
        :param group_name: A label to assign to orders submitted to the exchange for debug / tracking purposes.
        """
        return Order(self, **kwargs)

    def sign(self):
        return -1 if self.evaluate(0) < 0 else 1
    
    def inv_sign(self):
        return self.sign() * -1

    def abs(self):
        # Returns the absolute valued version of the security
        abs_evaluate = lambda sign: abs(self.evaluate(sign))
        return Security(self._ticker, self._exchange, evaluate=abs_evaluate, trade_costs=self.trade_costs, composition=self.composition, rebate = self.rebate)

     # NOTE: This is some cleanup code that is not really needed yet
    
    def get_tenders(self):
        return self._exchange._tenders[self._ticker]

    # def new_from_state(self, kwarg_mods={}):
    #     """
    #     :param kwarg_mods: a dictionary of keyword arguments of Security.__init__ to replace.
    #     :return a copy of the order's state
    #     """
    #     state = {
    #         'args':[self._ticker, self._exchange], 
    #         'kwargs': {'evaluate': self.evaluate, 'trade_costs': self.trade_costs, 'composition': self.composition, 'rebate': self.rebate}
    #     }

    #     state['kwargs'] = {**state['kwargs'], **kwarg_mods} # Overwrites optional arguments where appropriate

    #     return Security(*state['args'], **state['kwargs'])

class ExchangeConnection:
    def __init__(self, uri='ws://localhost:5678/trader', app_uri='ws://localhost:6789/frontend', enable_app=True, name='default_trader', setup_event=None):
        """
        Note to actually start the server connection we must call the async
        (self).connect_to_server() function
        """
        # All updated asynchronously
        self._LOBS = {} # Temp Variable for debug only
        self._tape = [] # Ticker Tape
        self._tenders = {} # Tender Orders by ticker

        self.name = name # A simple id for the trader

         # A list of OrderSpec's awaiting post to backend
        self._orders_to_dispatch = []
        self._tenders_to_dispatch = []
        self._cancellations_to_dispatch = []
        self._tender_completed_events = {} # Triggers passed from Tender class
        self._order_completed_events = {} # Triggers passed from Order class
        self._cancellation_completed_events = {} # Triggers passed from Order class

        # Handling pending complex limit orders events
        self._pending_complex_limit_events = {}

        # Tracking of open, completed and cancelled orders
        self._open_orders = {} # key = order_id
        self._completed_orders = {} # key = order_id
        self._cancelled_orders = {}
        
        self._tid = None # trader id
        self._securities = [] # Ticker ids
        self._security_objects = {} # Dict of Secuirty's
        self._risk = None
        self._pnl = {} # key is ticker
        self._uri = uri # backend web sockect address
        self._internal_next_order_id = 0 # Yields the next order id

        # Internal premeptive risk management
        # Assumes full and instantaneous execution of trades
        # without slippage - works as an internal risk limit safe guard
        self._theoretical_transaction_reccords = {}
        self._theoretical_pnls = {}
        self._theoretical_risk = TraderRisk(0,0,0,0,0)

        # VueJs App
        self._app_uri = app_uri
        self._enable_app = enable_app
        self._products = []

        # Time tracking
        self._exchange_open_time = 0

        # Connection Established event
        self._setup_event = setup_event

    async def connect_to_server(self):
        print("Connecting to backend...") 
        # Security [UNUSED]
        # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # ssl_context.load_verify_locations(pathlib.Path("ssl_cert/cert.pem"))
        # async with websockets.connect(self._uri, ssl = ssl_context) as ws:
        print("Connecting to %s" % self._uri)
        async with websockets.connect(self._uri, max_size= None) as ws:
            
            # First message recieved on connecting is your trader id
            # Note losing connection to the server will be fatal
            # As you will not be able to rejoin with the same id.
            # TODO: THINK ABOUT THIS
            config = json.loads(await ws.recv())
            self._config = config['data']
            self._tid = self._config['tid']
            self._exchange_open_time = self._config['exchange_open_time']
            self._securities = self._config['exchange']['securities']
            self._security_objects = {ticker: Security(ticker, self) for ticker in self._securities}

            self._tenders = {ticker: asyncio.Queue() for ticker in self._securities}
            self._has_new_tender = {ticker: asyncio.Event() for ticker in self._securities}
            
            # Init risk management
            for ticker in self._securities:
                self._theoretical_pnls[ticker] = TickerPnL(ticker,0,0,0,0)
                self._theoretical_transaction_reccords[ticker] = {'BUY':{'sum_qty':0, 'sum_qty_price':0,'transactions':[]},'SELL':{'sum_qty':0, 'sum_qty_price':0,'transactions':[]}}

            risk_limits = self._config['exchange']['risk_limits']
            self._risk_limits = to_named_tuple(risk_limits, RiskLimits)

            # Tell the trader using this connection that the connection is ready
            if self._setup_event: self._setup_event.set() 

            # Wrapper if using the vuejs app.
            if self._enable_app:
                async with websockets.connect(self._app_uri, max_size= None) as ws_app:
                    # Send tid to update trader window in app.
                    await ws_app.send(json.dumps({'type':'config', 'data':{'tid':self._tid}}))

                    # We need the update state to be on a seperate loop as it has 
                    # to wait on messages from the server indefinitely
                    await asyncio.gather(self.update_state(ws, ws_app), self.dispatch_messages(ws), self.dispatch_products_to_app(ws_app))
                    # while True:
                    #     print("Start frontend loop")
                    #     await asyncio.gather(self.update_state(ws, ws_app), self.dispatch_orders(ws), self.dispatch_tenders(ws), self.dispatch_cancellations(ws))
                    #     print("End frontend loop")
            else:
                await asyncio.gather(self.update_state(ws), self.dispatch_messages(ws))
                # while True:
                #     # Route messages to the correct place
                #     # -> Limit Order Books
                #     # -> Order Fill
                #     # -> Tape 
                #     # Update our book keeping mechanism
                #     # TODO Eventually refactor this looping into async queues for greater eficiency
                #     await asyncio.gather(self.update_state(ws), self.dispatch_orders(ws), self.dispatch_tenders(ws), self.dispatch_cancellations(ws))            
    
     # TODO: Refactor this pattern its getting repetitive

    def add_order_batch(self, orders, events):
        self._order_completed_events = {**self._order_completed_events, **events}
        self._orders_to_dispatch = self._orders_to_dispatch + orders
        
        for order_spec in orders:
            self.update_pnls_after_order(order_spec) 

    def cancel_orders(self, orders, events):
        # A list of orderSpecs is accepted
        self._cancellation_completed_events = {**self._cancellation_completed_events, **events}
        self._cancellations_to_dispatch = self._cancellations_to_dispatch + orders

    def accept_tender(self, tender_order, event):
        self._tender_completed_events[tender_order.tender_id] = event
        self._tenders_to_dispatch.append(tender_order)
        self.update_pnls_after_tender_accept(self._tid, tender_order)

    async def dispatch_orders(self, ws):
        while len(self._orders_to_dispatch) > 0:
            order = self._orders_to_dispatch.pop(0)
            json_order = dict(order._asdict())

            await ws.send(json.dumps({'type':'add_order', 'data': json_order}))

    async def dispatch_cancellations(self, ws):
        while len(self._cancellations_to_dispatch) > 0:
            order = self._cancellations_to_dispatch.pop(0)
            json_order = dict(order._asdict())

            await ws.send(json.dumps({'type':'cancel_order', 'data': json_order}))

    async def dispatch_tenders(self, ws):
        while len(self._tenders_to_dispatch) > 0:
            tender = self._tenders_to_dispatch.pop(0)
            json_order = dict(tender._asdict())

            await ws.send(json.dumps({'type':'accept_tender', 'data': json_order, 'user_utc_time': time(), 'exchange_time': self.get_exchange_time()}))

    def update_complex_lob_events(self):
        pending = []
        for complex_event in self._pending_complex_limit_events:
            if complex_event.lob_condition():
                complex_event.event.set()
            else:
                pending.append(complex_event)

        self._pending_complex_limit_events = pending

    async def dispatch_messages(self, ws):
        while True:
            await asyncio.gather(self.dispatch_orders(ws), self.dispatch_tenders(ws), self.dispatch_cancellations(ws))

    async def dispatch_products_to_app(self, ws_app, update_delay = 1):
         while True:
            for security, prefix in self._products:
                best_bid = security.evaluate(1)
                best_ask = security.evaluate(-1)
                ticker = security._ticker

                # Updates every second.
                data = {'ticker': prefix + ': ' + ticker, 'timestamp': floor(time() - self._exchange_open_time), 'best_bid': best_bid, 'best_ask': best_ask}
                await self.pass_to_app(ws_app, 'product_update', data)

            await asyncio.sleep(update_delay)

    async def update_state(self, ws, ws_app = None):
        while True:
            state = json.loads(await ws.recv())
            s_type, data = state['type'], state['data']

            if s_type == 'LOBS':
                # Overwrites old limit order books where they already exist
                self._LOBS = {**self._LOBS, **data}
                self.update_complex_lob_events() # Updates price based triggers
            elif s_type == 'tape':
                self._tape = self._tape + data
            elif s_type == 'order_opened':
                order_id = data['order_id']
                new_order = to_named_tuple(data, ExchangeOrder)

                self._open_orders[order_id] = new_order
                
                order_key = cast_named_tuple_to_dict(new_order, OrderKey)
                await self.pass_to_app(ws_app, 'order_opened', order_key)
            elif s_type == 'order_cancelled':
                success = data['success']
                order_id = data['order_spec']['order_id']

                if success == False:
                    warnings.warn('Order with id: %s was already filled by the time you cancelled it! This is not serious but something to be concerned about if this is a very frequent! We will proceed for now as if it had been cancelled (But clearly this needs fixing)...')
                else:
                    self._cancellation_completed_events[order_id].set() # Set cancellation flag

                    # Some general state management NOTE I think this is probably unused
                    self._cancelled_orders[order_id] = self._open_orders[order_id]

                    # TODO We will still keep it in open orders for the moment
                    # Until we can figure out how to handle out of sequence fills
                    # and cancellations
                    # del(self._open_orders[order_id])              
            elif s_type == 'order_fill':
                # 1. Get the qty, price of fill, order id [x]
                # 2. update the open order [x]
                # 3. if it has been fully filled close the order [x]
                # 4. Run book keeper to update our gross / net positions [o]
                transaction = to_named_tuple(data, Transaction)
                order_id = transaction.order_id
                existing_order = self._open_orders[order_id]
                total_filled = existing_order.qty_filled + transaction.qty

                updated_order = existing_order._replace(qty_filled = total_filled)
                
                # Partial fill
                partial_fill = updated_order.qty_filled < existing_order.qty

                if partial_fill: 
                    self._open_orders[order_id] = updated_order
                # Order completed
                else:
                    self._order_completed_events[order_id].set() # Change flag
                    self._completed_orders[order_id] = updated_order
                    del(self._open_orders[order_id])

                completed_order = named_tuple_to_dict(updated_order)
                
                msg_type = 'order_fill' if partial_fill else 'order_completed'
                pass_data ={'order':completed_order, 'transaction': data}
                await self.pass_to_app(ws_app, msg_type, pass_data)
            elif s_type == 'order_failed':
                warnings.warn("Order %s failed to be processed as it exceeded risk limits fix your broken code :) we don't do any nice handling of this!", data)
            elif s_type == 'current_time':
                print("Time since last current time update: %.3f" % (data - self.get_exchange_time()))
                # self.get_exchange_time() = data
            elif s_type == 'pnl':
                ticker_pnl = to_named_tuple(data, TickerPnL)
                self._pnl[ticker_pnl.ticker] = ticker_pnl
                await self.pass_to_app(ws_app, s_type, data)
            elif s_type == 'risk':
                self._risk = to_named_tuple(data, TraderRisk)
                await self.pass_to_app(ws_app, s_type, data)
            elif s_type == 'tender':
                tender = to_named_tuple(data, TenderOrder)
                await self._tenders[tender.ticker].put(tender)
            elif s_type == 'tender_fill': # When your tender order acceptance has been processed
                tender = to_named_tuple(data, TenderOrder)
                self._tender_completed_events[tender.tender_id].set()
            elif s_type == 'tender_rejected':
                tender = to_named_tuple(data, TenderOrder)
                warnings.warn('Tender [%s] for ticker [%s] was rejected, this is an anti-tamper mechanism warning. You must accept a tender before it expires. Note your code will likely fail now as it will be still waiting for the tender complete flag. To fix this you should allow a greater buffer between a tender\'s expiration and your acceptance' % (tender.tender_id, tender.ticker))

    def register_product(self, security, prefix=""):
        """
        Registers a product with the frontend client so that a chart can be drawn of the compound price.
        """
        if self._enable_app:
            self._products.append((security, prefix))
           
    # ------ Helper Methods -----
    
    # def clearout_old_tenders(self):
    #     # Oldest tenders nearer the front of the list
    #     # Newest close to the back (appened)
    #     for ticker in self._tenders:
    #         ticker_tenders = self._tenders[ticker]
    #         while len(ticker_tenders) > 0:
    #             if ticker_tenders[0].expiration_time < self.get_exchange_time():
    #                 ticker_tenders.pop(0)
    #             else:
    #                 break

    async def pass_to_app(self, ws_app, s_type, data):
        if self._enable_app:
            await ws_app.send(json.dumps({'type': s_type, 'data': data}))

    def get_trade_cost(self, ticker):
        return self._securities[ticker]['trade_cost']

    def get_rebate(self, ticker):
        return self._securities[ticker]['rebate']

    def get_LOB(self, ticker):
        return to_named_tuple(self._LOBS[ticker], LOB)
    
    def get_tape(self):
        return self._tape

    def get_exchange_time(self):
        return time() - self._exchange_open_time

    def add_complex_event_condition(self, complex_event):
        self._pending_complex_limit_events.append(complex_event)

    def get_next_id(self):
        self._internal_next_order_id += 1
        return int(str(self._tid) + str(self._internal_next_order_id))

    def update_pnls_after_order(self, order_spec):
        """
        Updates pnl, risk, transaction records for traders on both sides of the trade
        :param transaction_pair: of type TransactionPair
        """
        # action of the liquidity taker
        notional_transaction = Transaction(order_spec.tid, order_spec.order_id, order_spec.qty, order_spec.price, time())
        
        self.update_trader_transaction_record(notional_transaction, order_spec.action, order_spec.ticker)
        self.recompute_trader_pnl(order_spec.ticker)

    def update_pnls_after_tender_accept(self, tid, tender_order):
        current_time = self.get_exchange_time()
        tender_transaction = Transaction(tid, tender_order.tender_id, tender_order.qty, tender_order.price, current_time)
        self.update_trader_transaction_record(tender_transaction, tender_order.action, tender_order.ticker)
        self.recompute_trader_pnl(tender_order.ticker)

    def update_trader_transaction_record(self, transaction, action, ticker):
        """
        Updates trade risk, pnl and transaction records
        :param transaction: A trader's transaction of type Transaction
        :param action: Either BUY or SELL
        :param ticker: A security ticker string
        """
        # Allocate the transaction so we can trace it later and perform computations
        ticker_record = self._theoretical_transaction_reccords[ticker]
        side_record = ticker_record[action] # Buy or sell transaction record
        transactions = side_record['transactions']

        transactions.append(transaction)

        # Saves on expensive computations later in recompute_trader_pnl
        side_record['sum_qty'] += transaction.qty
        side_record['sum_qty_price'] += transaction.qty * transaction.price

    def recompute_trader_pnl(self, ticker):
        """
        Recomputes the PNL and Risk metrics and notifies the trader of the change
        :param tid: a trader id
        """
        ticker_record = self._theoretical_transaction_reccords[ticker]

        # Now let us recompute the pnl
        exchange_config = self._config['exchange']
        securities_config = exchange_config['securities']
        contract_config = securities_config[ticker]
        contract_point_value = contract_config['contract_point_value']
        contract_currency = contract_config['quote_currency']
        base_currency = exchange_config['base_currency']

        best_bid, best_ask = self._security_objects[ticker].evaluate(1), self._security_objects[ticker].evaluate(-1), 

        total_buy_qty = ticker_record['BUY']['sum_qty']
        total_sell_qty = ticker_record['SELL']['sum_qty']
        total_buy_qty_price =  ticker_record['BUY']['sum_qty_price']
        total_sell_qty_price =  ticker_record['SELL']['sum_qty_price']

        # This is fine as then there will be no realised 
        if total_buy_qty > 0:
            # avg_buy_price = sum([transaction.price * transaction.qty for transaction in ticker_record['BUY']['transactions']]) / total_buy_qty
            avg_buy_price = total_buy_qty_price / total_buy_qty
        else:
            avg_buy_price = 0
        
        if total_sell_qty > 0:
            # avg_sell_price = sum([transaction.price * transaction.qty for transaction in ticker_record['SELL']['transactions']]) / total_sell_qty
            avg_sell_price = total_sell_qty_price / total_sell_qty
        else:
            avg_sell_price = 0

        if total_buy_qty == 0 or total_sell_qty == 0:
            realised_pnl_points = 0 # Nothing has yet been realised
            realised_pnl_contract_currency = 0
        else:
            realised_pnl_points = (avg_sell_price - avg_buy_price) * min(total_buy_qty, total_sell_qty)
            realised_pnl_contract_currency = round(realised_pnl_points * contract_point_value, 2)
        
        # We assume that trades may be settled at market close at the midprice to avoid any spurious 
        # edge cases
        net_position = total_buy_qty - total_sell_qty
        avg_open_price = avg_buy_price * int(net_position > 0) + avg_sell_price * int(net_position < 0)
        theoretical_exit_price = (best_ask + best_bid) / 2 
        
        unrealised_pnl_points = (theoretical_exit_price - avg_open_price) * net_position
        unrealised_pnl_contract_currency = round(unrealised_pnl_points * contract_point_value,2)
        
        total_pnl_points = unrealised_pnl_points + realised_pnl_points
        total_pnl_contract_currency = round(total_pnl_points * contract_point_value,2) # Pnl only stated to 2d.p

        # EX: PNL is in USD and Base is CAD
        # Direct Quote of USD => best ask = # CAD Required to buy 1 USD
        # Thus we are selling USD at market so we take the best bid

        conversion = 1 if base_currency == contract_currency else self._security_objects[contract_currency].evaluate(1) # Best bid price
        
        unrealised_pnl_base_currency = unrealised_pnl_contract_currency * conversion
        realised_pnl_base_currency = realised_pnl_contract_currency * conversion
        pnl_total_base_currency = total_pnl_contract_currency * conversion

        # PnL history by ticker

        # Update ticker pnl
        self._theoretical_pnls[ticker] = TickerPnL(ticker, net_position, unrealised_pnl_base_currency, realised_pnl_base_currency, pnl_total_base_currency)

        # Recompute risk
        overall_net_position = sum([pnl.net_position for ticker, pnl in self._theoretical_pnls.items()])
        overall_gross_position = sum([abs(pnl.net_position) for ticker, pnl in self._theoretical_pnls.items()])
        overall_unrealised = sum([pnl.unrealised for ticker, pnl in self._theoretical_pnls.items()])
        overall_realised = sum([pnl.realised for ticker, pnl in self._theoretical_pnls.items()])
        overall_pnl = sum([pnl.total_pnl for ticker, pnl in self._theoretical_pnls.items()])

        # pnl_history = trader_risk.pnl_history
        # # We avoid deeply nesting named tuples as this can be painful for data transfer
        # pnl_history.append({'time':current_time,'value':overall_pnl})
        
        # self._risk[tid] = TraderRisk(overall_net_position, overall_gross_position,overall_unrealised, overall_realised, overall_pnl, pnl_history)

        self._theoretical_risk = TraderRisk(overall_net_position, overall_gross_position,overall_unrealised, overall_realised, overall_pnl)

        # TODO: Compute SHARPE, CALMAR, SORTINO, etc

    def orders_conform_to_trader_risk_limits(self, order_specs):
        change_in_net_positions = {ticker: 0 for ticker in self._securities}
        
        for order_spec in order_specs:
            trader_risk = self._theoretical_risk
            multiplier = self._securities[order_spec.ticker]['risk_limit_multiplier']
            weighted_qty = multiplier * order_spec.qty
            signed_qty = weighted_qty if order_spec.action == 'BUY' else -1 * weighted_qty
            
            change_in_net_positions[order_spec.ticker] += signed_qty

        is_within_net_limit = True
        is_within_gross_limit = True

        for ticker in self._securities: 
            security_positions = self._theoretical_transaction_reccords[ticker]
            security_net_pos = security_positions['BUY']['sum_qty'] - security_positions['SELL']['sum_qty']

            new_security_net_pos = security_net_pos + change_in_net_positions[ticker]
            gross_change = abs(new_security_net_pos) - abs(security_net_pos)

            is_within_net_limit = is_within_net_limit and abs(trader_risk.net_position + signed_qty) < self._risk_limits.net_position
            is_within_gross_limit = is_within_gross_limit and abs(trader_risk.gross_position + gross_change) < self._risk_limits.gross_position

        return is_within_net_limit and is_within_gross_limit

class Order:
    def __init__(self, security, qty=1, order_type="MKT", can_execute = None, direction = 1, on_complete = None, price_fn = None, qty_fn = None, group_name="default", timeout=None, timeout_fn=None, await_fills=True):
        """
        :param security: A security object
        :param qty: The amount to buy / sell of security
        :param qty_fn: A generalisation of qty which is a function which dynamically returns qty when called
         Note that qty will be implicityly converted to a qty_fn. Either qty or qty_fn must be specified
        :param order_type: One of MKT, LMT, TENDER
        :param direction: 1 for Buy, -1 for Sell
        :param can_execute: A boolean valued function, which it is preferred to be set using % operator. Although
        internally the condition passed to % will be implemented by passing the argument
        :param on_complete: A function that returns another order.execute (Should never be required explictly)
        :param price: A function which accepts (direction ~ int, evaluate ~ Security.evaluate) and returns a lmt price
        :param group_name: A label to assign to orders submitted to the exchange for debug / tracking purposes.
        :param timeout: Number of seconds to wait for order fill to occur, on failing to fill in entirety on_timeout will be called
        :param timeout_fn: will be called as on_timeout when the timeout elapses. Must be async with args (filled, unfilled) which are dicts containing order specs. NOTE: timeout_fn if triggered overrides any implemented .then() / _on_complete.
        :param await_fills: when False, execution will not block waiting for orders to be filled.
        """

        if price_fn == None and order_type == 'LMT':
            raise ValueError("A limit price must be specified for a limit order!")
        
        if qty_fn == None and qty == None:
            raise ValueError("Either qty of qty_fn must be specified!")
        
        if qty_fn != None:
            # prevents any floating point artifacts from occurring 
            def qtf_fn_cast_to_int():
                return int(qty_fn())

            self.evaluate_qty = qtf_fn_cast_to_int
        else:
            def compute_qty_base():
                return int(qty)

            self.evaluate_qty = compute_qty_base

        self._security = security
        self.order_type = order_type
        self._direction = direction # Buy = 1, Sell = -1
        self.get_target_price = price_fn
        self.group_name = group_name
        self._timeout = timeout
        self._await_fills = await_fills

        if timeout_fn == None and self._timeout != None:
            raise ValueError('If a timeout is specified you MUST specify an async timeout_fn')
        elif timeout_fn != None:
            self._on_timeout = timeout_fn
        else:
            self._on_timeout = None

        if type(on_complete) == type(None):
            async def complete():
                return True

            self._on_complete = complete # On completing order execution
        else:
            self._on_complete = on_complete

        if type(can_execute) == type(None):
            def can_execute_base():
                return True

            self.can_execute = can_execute_base
        else:
            self.can_execute = can_execute   

        self.config = {} 

    def new_from_state(self, kwarg_mods={}):
        """
        :param kwarg_mods: a dictionary of keyword arguments of Order.__init__ to replace.
        :return a copy of the order's state
        """
        state = {
            'args':[self._security], 
            'kwargs': {
            'order_type': self.order_type, 'can_execute': self.can_execute, 'direction': self._direction, 'on_complete': self._on_complete, 'price_fn': self.get_target_price, 'qty_fn': self.evaluate_qty, 'group_name': self.group_name, 'timeout': self._timeout, 'timeout_fn':self._on_timeout, 'await_fills':self._await_fills}
        }

        state['kwargs'] = {**state['kwargs'], **kwarg_mods} # Overwrites optional arguments where appropriate

        return Order(*state['args'], **state['kwargs'])

    def __rmul__(self, other):
        # This is for premultiplying by -1 or 1 to change the direction from the default BUY
        if type(other) != float and type(other) != int:
            raise ValueError('Can only premultiply a security by a number!')
        
        new_direction = -1 if other < 0 else 1
        return self.new_from_state(kwarg_mods = {'direction': new_direction})

    def __neg__(self):
        return self.__rmul__(self._direction * -1)

    def unwind(self):
        # TODO: This is a very simple implementation
        # Rework this to incorporate when orders have only partially filled.
        return self.__neg__()

    def __mod__(self, condition):
        # This checks whether the condition on the other side of the modulus is satisfied
        def can_execute():
            return self.can_execute() and condition()

        return self.new_from_state(kwarg_mods = {'can_execute': can_execute})

    def sign(self):
        return self._direction
    
    def inv_sign(self):
        return self._direction * -1

    def trade_costs(self):
        """
        Computes the cost of executing the trade. 
        Note that a negative cost due to rebates implies you 
        get paid to execute the trade
        """

        if self.order_type == "LMT":
            return -1 * self._security.rebate() * self.evaluate_qty()
        elif self.order_type == "MKT":
            return self._security.trade_costs() * self.evaluate_qty()
        else:
            return 0

    @staticmethod
    def price_to_price_fn(price):
        def price_fn(direction, evaluate_fn):
            return price

        return price_fn

    async def execute(self):
        """
        Executes the order, computing the individual secuirty quantiteis and directions.
        Sends the orders to the exchange api for posting to the server.
        """
        
        if not self.can_execute():
            return False
        
        composition = self._security.composition(self._direction)
        
        # Orders + Events to send to server + Order Fill Task Events to Await
        orders, events, order_fill_tasks = [], {}, []
        
        # Seperate tracking of orders remaining to be filled in case of timeout
        # We do this separately to avoid breaking anything in the previous line
        unfilled = {}
        filled = {}

        # Keep track of order state so that we can manage unfilled tasks on timeoute
        async def fill_waiter(event, order):
            unfilled[order.order_id] = order # Neat way to track these fills without creating a mess
            await event.wait()
            del(unfilled[order.order_id]) # Order filled (Won't be called if timeout occurs later)
            filled[order.order_id] = order

        # Compose order
        # Note: We also need to take into account execution of complex composed orders
        # Market orders will execute at market and report back
        # Limit orders will need to execute within 3% of the composed price
        # Our challenge is to leave the backend alone and manage this execution risk

        # Solution:
        # 1. If its a complex order, check if there is sufficient liquidity in the book on all legs
        # such that the target limit price may be achieved +- 3%
        #   YES: Execute the order as a market order
        #   NO: Delay execution until 1 is true
        if self.order_type == "CMPLX":
            # We have a complex LMT order
            # We need to evaluate the target price and store this value
            # Otherwise we end up chasing our tail with revevaluations
            # Note we need to invert the direction as we are going to be 
            # crossing the spread with a market order.
            target_price = self.get_target_price(-1*self._direction, self._security.evaluate)
            
            # Define the condition for execution of the limit order
            def execution_condition():
                # Ensure that we execute at or better than the notional target price
                mkt_price = self._security.evaluate(-1*self._direction)
                price_delta = target_price - mkt_price 
                return self._direction * price_delta >= 0

            # Await the exchange to validate that the price is close to the desired limit
            wait_for_execution_condition_event = asyncio.Event()
            self._security._exchange.add_complex_event_condition(ComplexEvent(execution_condition, wait_for_execution_condition_event))
            await wait_for_execution_condition_event.wait()
        
        # Dispatch Orders
        for ticker, composition_meta in composition.items():
            order_type = self.order_type

            if order_type == "CMPLX":
                # Since we can only simulate Complex Orders from the frontend
                # without any exchange code specifically for complex multi legged order matching
                # We will execute knowing that the current market price is close to the desired LMT.
                order_type = "MKT"
                price = composition_meta.price
            elif order_type == "LMT":
                # Simple LMT Order
                price = self.get_target_price(self._direction, self._security.evaluate)
            else:
                # MKT or Complex LMT
                price = composition_meta.price

            weighting = composition_meta.weight
            action = "BUY" if weighting > 0 else "SELL"

            order_id = self._security._exchange.get_next_id()
            order_qty = int(self.evaluate_qty() * abs(weighting)) # Essential to avoid residual fill bugs
            spec = OrderSpec(ticker, self._security._exchange._tid, order_id, order_type, order_qty, action, price, self.group_name)
            
            order_filled_event = asyncio.Event()

            # Spawn a Task to wait until 'event' is set.
            # Creating the task delays the execution of this function to later
            waiter_task = asyncio.create_task(fill_waiter(order_filled_event, spec))

            order_fill_tasks.append(waiter_task)
            events[order_id] = order_filled_event
            orders.append(spec)
        
        # Check Risk Limits
        if not self._security._exchange.orders_conform_to_trader_risk_limits(orders):
            return False

        # Execute order
        self._security._exchange.add_order_batch(orders, events)
        # Wait for completion of order and call the next order if applicable        
        try:
            if self._await_fills:
                # Note if self._timeout is none is just waits indefinitely
                done, pending = await asyncio.wait(order_fill_tasks, timeout=self._timeout)
                
                if len(pending) > 0:
                    for task in pending:
                        task.cancel()
                    raise asyncio.TimeoutError()
                    
            await self._on_complete() # This is deliberately outside the if, so that 
            # the possibility exists to use .then() with _await_fills = False
        except asyncio.TimeoutError:
            await self._on_timeout(filled, unfilled)
            # Note if a timeout occurs this is viewed as an alternative to _on_complete
            # as we expect different logic to handle this.

        return True # Returns Success

    def then(self, order):
        """
        Executes the order specified once the current one (self) has been filled
        :param order: of type Order
        """
        return self.new_from_state({'on_complete': order.execute})

    async def execute_on_interval(self, delay = 1):    
        while True:
            await self.execute_later(delay)

    async def execute_later(self, delay = 1):
        if delay > 0:
            await asyncio.sleep(delay)

        return await self.execute()

class Tender():
    # TODO Refactor Tender and Order into an ABC
    def __init__(self, security, can_execute = None, on_complete = None, group_name="tender"):
        """
        :param security: A security object for which to listen for tenders
        :param can_execute: A boolean valued function, which it is preferred to be set using % operator. It must have the arguments (price, qty, direction) referring to the direction of the tender.
        :param on_complete: A function that returns another order.execute (Should never be required explictly) use .then instead
        :param group_name: A label to assign to orders submitted to the exchange for debug / tracking purposes.
        """
        if type(on_complete) == type(None):
            async def complete():
                return True

            self._on_complete = complete # On completing order execution
        else:
            self._on_complete = on_complete

        if type(can_execute) == type(None):
            def can_execute_base(price, qty, direction):
                return True

            self.can_execute = can_execute_base
        else:
            self.can_execute = can_execute

        self._security = security
        self.group_name = group_name

    def new_from_state(self, kwarg_mods={}):
        """
        :param kwarg_mods: a dictionary of keyword arguments of Order.__init__ to replace.
        :return a copy of the order's state
        """
        state = {
            'args':[self._security], 
            'kwargs': {'can_execute': self.can_execute, 'on_complete': self._on_complete,'group_name': self.group_name}
        }

        state['kwargs'] = {**state['kwargs'], **kwarg_mods} # Overwrites optional arguments where appropriate

        return Tender(*state['args'], **state['kwargs'])

    def __mod__(self, condition):
        # This checks whether the condition on the other side of the modulus is satisfied
        def can_execute():
            return self.can_execute() and condition()

        return self.new_from_state(kwarg_mods = {'can_execute': can_execute})

    def then(self, hedging_fn):
        """
        Executes the hedging function once the current tender has been accepted
        :param hedging_fn: Takes the TenderOrder as an argument, must be async function.
        """
        return self.new_from_state({'on_complete': hedging_fn})
    
    async def execute(self, workers=10, timeout=30):
        """
        Executing a tender lets it listen for institutional orders
        then act on one if it is priced attractively. It 
        decides this via the can_execute function.
        Note generally we will want to use execute_on_interval
        as execute will only listen once.
        Note this function will await until new tenders arrive.
        """
        # Note this code will break if the exchange is not running
        # it is assume that the user will be responsible and 
        # not run this code outside of a live exchange env.

        # Will wait here until a new tender arrives
        tender_q = self._security.get_tenders()
        hedging_coroutines = asyncio.Queue()

        # TODO deal with risk management of execution appropriately
        async def process_tenders():
            while True:
                tender = await tender_q.get() 
                direction = self.get_direction(tender)

                if self.can_execute(tender.price, tender.qty, direction):
                    if tender.expiration_time < self._security._exchange.get_exchange_time() + self._security._tender_rejection_window:
                        warnings.warn("Tender order expired before you could process it, this was handled gracefully but you should really fix your slow tender processing code, or adjust the tender rejection window.")
                    else:
                        tender_accepted_event = asyncio.Event()
                        self._security._exchange.accept_tender(tender, tender_accepted_event)

                        await tender_accepted_event.wait()
                        await hedging_coroutines.put(self._on_complete(tender))

                        # tender_q.task_done() # Tell the q we've accepted it and move onto the next order
                        # await self._on_complete(tender) # Deal with filling the hedge when a fill becomes feasible
             
        # Separating out the hedging logic from the main tender processing
        # Prevents a scenario where hedging is blocking tender evaluation
        # thus leading to a backlog and loss of business due to tender 
        # time sensitive nature
        async def hedge_tender():
            while True:
                hedge = await hedging_coroutines.get()
                await hedge # Sometimes this will be practically instant if the hedge orders are no_await = True
            
        # We want muliple workers to prevent tenders being processed to slowly
        processors = asyncio.gather(*[process_tenders() for _ in range(workers)])
        hedgers = asyncio.gather(*[hedge_tender() for _ in range(workers)])
        await asyncio.gather(processors, hedgers)

    @staticmethod
    def get_direction(tender_order):
        return 1 if tender_order.action == 'BUY' else -1

    @staticmethod
    def get_inv_direction(tender_order):
        return -1 if tender_order.action == 'BUY' else 1