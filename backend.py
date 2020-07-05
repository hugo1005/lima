import numpy as np
import asyncio
import websockets
import json
import ssl
import pathlib
import warnings
import time
from luno_python.client import Client
from random import normalvariate, gammavariate, betavariate, choice
from numpy.random import poisson
from scipy.stats import gamma
from math import log10, floor

from shared import LOB, OrderSpec, ExchangeOrder, Transaction, TransactionPair, ExchangeOrderAnon, TapeTransaction, MarketBook, TickerPnL, TraderRisk, TenderOrder, RiskLimits
from shared import to_named_tuple, update_named_tuple, named_tuple_to_dict, LunaToExchangeOrder, LunaToExchangeTransactionPair, KrakenToExchangeOrder
# from traders import GiveawayTrader

from aiodebug import log_slow_callbacks
import logging

# logging.basicConfig(filename='./profiles/backend.log', level=logging.INFO)

# Profiling command line prompts
# python3 -m cProfile -s filename -o profiles/backend_long_run.cprof backend.py
# pyprof2calltree -k -i profiles/backend_long_run.cprof

class HalfOrderbook:
    def __init__(self, book_side, starting_best_price):
        self.anonymised_lob = {}
        self.lob = {}

        self.book_side = book_side # bids or asks
        self.book_depth = 0 # Number of different prices
        self.num_orders = 0
        self.book_volume = 0 # Limit order book volume only
        self.best_price = starting_best_price
        self._market_order_q = []
        self.anonymised_market_order_q = []

    def anonymise(self, order):
        order_dict = dict(order._asdict())
        return dict(to_named_tuple(order_dict, ExchangeOrderAnon)._asdict())

    def add_order(self, order):
        # Update Best Quote
        if order.order_type == "MKT":
            self._market_order_q.append(order)
            self.anonymised_market_order_q.append(self.anonymise(order))

        elif order.order_type == "LMT":
            if order.price not in self.lob:
                self.lob[order.price] = [] 
                self.anonymised_lob[order.price] = []

            self.lob[order.price].append(order)
            self.anonymised_lob[order.price].append(self.anonymise(order))
            self.book_volume += order.qty
        else: 
            warnings.warn('An unkown order type [%s] was used and could not be executed' % order.action, UserWarning)

        self.recompute_stats()

    def cancel_order(self, order_spec):
        order_id = order_spec.order_id
        price = order_spec.price

        if order_spec.order_type == 'LMT':
            # Edge case (Order already processed)
            if price not in self.lob:
                return False

            # Remove the order
            order_match = list(filter(lambda x: x.order_id == order_id, self.lob[price]))
            if len(order_match) > 0:
                order = order_match[0]
                self.lob[price] = list(filter(lambda x: x.order_id != order_id, self.lob[price]))
                self.anonymised_lob[price] = list(filter(lambda x: x['order_id'] != order_id, self.anonymised_lob[price]))
                
                self.book_volume -= (order.qty - order.qty_filled) # Remove remainining liquidity

                # Remove the price if there is nothing available
                self.update_price(price)
                return True
            else:
                # Edge case (Order already processed)
                return False
        elif order_spec.order_type == 'MKT':
            order_match = list(filter(lambda x: x.order_id == order_id, self._market_order_q))

            if len(order_match) > 0:
                self._market_order_q = list(filter(lambda x: x.order_id != order_id, self._market_order_q))
                self.anonymised_market_order_q = list(filter(lambda x: x['order_id'] != order_id, self.anonymised_market_order_q))
                self.recompute_stats()
                return True
            else:
                return False

        return False

    def has_market_orders(self):
        return len(self._market_order_q) > 0

    def recompute_stats(self):
        # Prices in ascending order
        available_prices = sorted(self.lob)

        # Compute best price
        # Note: If there is no current prices we leave it unchanged as the 'last' best price
        if len(available_prices) > 0:
            self.best_price = available_prices[-1] if self.book_side == 'bids' else available_prices[0]
        
        # compute num orders
        self.num_orders = sum([len(self.lob[price]) for price in self.lob]) + len(self._market_order_q)
        self.book_depth = len(available_prices)

    def update_price(self, price):
        if len(self.lob[price]) == 0:
            del(self.lob[price])
            del(self.anonymised_lob[price])

        self.recompute_stats()

    def update_best_quote(self, quote):
        if quote.order_type == "MKT":
            if quote.qty - quote.qty_filled > 0:
                # Update the quote
                self._market_order_q[0] = quote
                self.anonymised_market_order_q[0] = self.anonymise(quote)
            else:
                # Remove the quote if it is filled entirely
                self._market_order_q.pop(0)
                self.anonymised_market_order_q.pop(0)

            # Update the statistics of the halfbook
            self.recompute_stats() 
        elif quote.order_type == "LMT":
            increase_in_filled_qty = quote.qty_filled - self.lob[self.best_price][0].qty_filled

            if quote.qty - quote.qty_filled > 0:
                # Update the quote
                self.lob[self.best_price][0] = quote
                self.anonymised_lob[self.best_price][0] = self.anonymise(quote)
            else:
                # Remove the quote if it is filled entirely
                self.lob[self.best_price].pop(0)
                self.anonymised_lob[self.best_price].pop(0)
        
            # Remove the price if there is nothing available
            # And implicity recomputes the stats
        
            self.update_price(self.best_price)    

            # Remove the filled amount - Note we are only tracking limit volume
            # id %s qty %s filled %s incre %s vol %s
            self.book_volume -= increase_in_filled_qty
            assert(self.book_volume >= 0)

    def get_best_quote(self):
        """
        Gets the best available quote from the halfbook using the
        price time priority queue protocol.
        :return quote: an ExchangeOrder or None if none available
        """

        # Implements a price time priority queue
        has_limit_order = self.best_price in self.lob
        has_market_order = len(self._market_order_q) > 0

        if has_limit_order and has_market_order:
            best_limit_order = self.lob[self.best_price][0] 
            best_market_order = self._market_order_q[0]

            limit_arrived_before_market = best_limit_order.submission_time < best_market_order.submission_time

            if limit_arrived_before_market:
                return best_limit_order
            else:
                return best_market_order

        elif has_limit_order:
            return self.lob[self.best_price][0] 
        elif has_market_order:
            return self._market_order_q[0]
        else:
            return None

class Orderbook:
    def __init__(self, config, time_fn):

        starting_price = config['starting_price']
        starting_spread = config['starting_spread']
        resolution = config['resolution']

        # Initial Fair Value
        # self._best_bid = starting_price - starting_spread/2
        # self._best_ask = starting_price + starting_spread/2

        self._bids = HalfOrderbook('bids', round(starting_price - starting_spread/2, resolution))
        self._asks = HalfOrderbook('asks',  round(starting_price + starting_spread/2, resolution))
        self.get_time = time_fn # Exchange time function

    def has_market_orders(self):
        # Checks both queues for market order availability
        return len(self._bids._market_order_q) > 0 or len(self._asks._market_order_q)
    
    def has_marketable_limit_orders(self):
        # Check if the spread has been crossed
        # and that limit orders exists
        has_limit_orders = self._bids.num_orders > 0 or self._asks.num_orders > 0
        spread_crossed = self._bids.best_price >= self._asks.best_price
        return has_limit_orders and spread_crossed

    def get_earliest_order(self, orders):
        earliest_order = None

        for order in orders:
            if type(earliest_order) == type(None):
                earliest_order = order
                continue

            if order.submission_time < earliest_order.submission_time:
                earliest_order = order

        return earliest_order
    
    def get_highest_priority_marketable_order(self):
        # Returns the price time priority best market order or marketable limit order
        
        best_market_orders = []
        best_limit_orders = []

        # Note a marketable limit order is crossing the bid ask spread
        # Thus it is creating a market at a better price thus will get priority
        # over market orders which do nothing to improve the price
        if self.has_marketable_limit_orders():
            # Both marketable limit and market orders potentially available
            # Note if the spread has been crossed it doesn't really matter what direction
            # we execute really because the other best quote is guarunteed to be traded with
            # but we write this to make it easier to understand the price time priority queue
            best_ask_order = self._asks.get_best_quote()
            best_bid_order = self._bids.get_best_quote()

            if best_bid_order: best_limit_orders.append(best_bid_order)
            if best_ask_order: best_limit_orders.append(best_ask_order)

        elif self.has_market_orders():
            # Only Market Orders Available
            if self._bids.has_market_orders() and self._asks.has_market_orders():
                best_ask_order = self._asks._market_order_q[0]
                best_bid_order = self._bids._market_order_q[0]
                best_market_orders = [best_ask_order, best_bid_order]
            elif self._asks.has_market_orders():
                best_market_orders = [self._asks._market_order_q[0]]
            elif self._bids.has_market_orders():
                best_market_orders = [self._bids._market_order_q[0]]
        
        # This is just for clarity of a single return statement
        return self.get_earliest_order(best_market_orders + best_limit_orders)
            
    def auction(self):
        """
        Executes market orders against the limit order halfbooks and updates book accordingly
        :return latest_transactions: A list of TransactionPairs completed
        """

        latest_transactions = []
        
        # My Thoughts
        # 1. Get Marketable Limit Orders in (price~N/A) time priority
        #   1.1 return the earliest marketable limit order
        # 2. Get the earliest market order
        # 3. select the earliest of the market and limit orders
        # 4. Execute the remaining code as before and loop
        
        while self.has_market_orders() or self.has_marketable_limit_orders():
            # Note this will be either a market order or a marketable limit orderr            
            market_order = self.get_highest_priority_marketable_order()
            halfbook = self._asks if market_order.action == "BUY" else self._bids
            # Exit if no market Liquidity
            if halfbook.num_orders == 0:
                break
            
            # Transact with best quote in book until filled or no market exists
            while True:
                # Exit if no market Liquidity
                if halfbook.num_orders == 0:
                    break
                
                # Note this technically can also be an opposing market order
                # If such an order is awaiting execution
                limit_quote = halfbook.get_best_quote()

                market_order_qty_remaining = market_order.qty - market_order.qty_filled
                limit_quote_qty_remaining = limit_quote.qty - limit_quote.qty_filled

                # Can only fill to the smallest of the two qty's
                fill_qty = min(market_order_qty_remaining, limit_quote_qty_remaining)
                fill_price = limit_quote.price

                # To avoid inequitable trading for both parties
                # We match the MKT MKT edge case at the midprice
                if limit_quote.order_type == 'MKT' and market_order.order_type == 'MKT':
                    fill_price = (limit_quote.price + market_order.price) / 2

                # Issue the transaction for distribution to traders
                # We deliberately duplicate some information for purposes of distribution
                # Action of a transaction is always in direction of the liquidity taker (market order)
                transaction_time =  self.get_time()
                maker = Transaction(limit_quote.tid, limit_quote.order_id, fill_qty, fill_price, transaction_time) 
                taker = Transaction(market_order.tid, market_order.order_id, fill_qty, fill_price, transaction_time)
                latest_transactions.append(TransactionPair(market_order.ticker, market_order.action, maker, taker, transaction_time))
                
                # Update Internal Order States
                market_order = update_named_tuple(market_order, {'qty_filled': market_order.qty_filled + fill_qty})
                limit_quote = update_named_tuple(limit_quote, {'qty_filled': limit_quote.qty_filled + fill_qty})

                # Update Market Order + Limit Order
                # Note this is a hack as the halfbook is intelligent enough to determine weather this 
                # is a marketable limit order or a market order
                market_order_hafbook = self._asks if market_order.action == "SELL" else self._bids
                market_order_hafbook.update_best_quote(market_order)
                halfbook.update_best_quote(limit_quote)

                # Order has been fully filled 
                # Exit the loop and get the next available order for auction
                if market_order.qty_filled >= market_order.qty:
                    break; 

        return latest_transactions
               
    def add_order(self, exchange_order):
        halfbook = self._bids if exchange_order.action == "BUY" else self._asks
        halfbook.add_order(exchange_order)
        
    def cancel_order(self, order_spec):
        if order_spec.order_type == "LMT" or order_spec.order_type == "MKT":
            halfbook = self._bids if order_spec.action == "BUY" else self._asks
            return halfbook.cancel_order(order_spec)
        else:
            warnings.warn('Order of type [%s] is not a cancellable type' % order_spec.action, UserWarning)
            return False
    
    def get_LOB(self):
        return LOB(self._bids.anonymised_lob, self._asks.anonymised_lob, self._bids.best_price, self._asks.best_price, self._bids.book_depth, self._asks.book_depth, self._bids.num_orders, self._asks.num_orders, self._bids.book_volume, self._asks.book_volume)

    def get_market_book(self):
        return MarketBook(self._bids.anonymised_market_order_q, self._asks.anonymised_market_order_q)

class LunaHalfOrderbook:
    def __init__(self, book_side):
        self.anonymised_lob = {}
        self.lob = {}

        self.book_side = book_side # bids or asks
        self.book_depth = 0 # Number of different prices
        self.num_orders = 0
        self.book_volume = 0 # Limit order book volume only
        self.best_price = 0
        self._market_order_q = []
        self.anonymised_market_order_q = []

    def anonymise(self, order):
        order_dict = dict(order._asdict())
        return dict(to_named_tuple(order_dict, ExchangeOrderAnon)._asdict())

    def add_order(self, order):
        # Update Best Quote
        if order.order_type == "MKT":
            self._market_order_q.append(order)
            self.anonymised_market_order_q.append(self.anonymise(order))

        elif order.order_type == "LMT":
            if order.price not in self.lob:
                self.lob[order.price] = [] 
                self.anonymised_lob[order.price] = []

            self.lob[order.price].append(order)
            self.anonymised_lob[order.price].append(self.anonymise(order))
            self.book_volume += order.qty
        else: 
            warnings.warn('An unkown order type [%s] was used and could not be executed' % order.action, UserWarning)

        self.recompute_stats()

    def get_order(self, order_id, order_type, price = -1):

        if order_type == 'LMT':
            if price > 0:
                order_match = list(filter(lambda x: x.order_id == order_id, self.lob[price]))
            else:
                all_orders = []
                for price in self.lob:
                    all_orders += self.lob[price]

                order_match = list(filter(lambda x: x.order_id == order_id, all_orders))
        else:
            order_match = list(filter(lambda x: x.order_id == order_id, self._market_order_q))

        return order_match[0] if len(order_match) > 0 else None

    def cancel_order(self, order_spec):
        order_id = order_spec.order_id
        price = order_spec.price

        if order_spec.order_type == 'LMT':
            # Edge case (Order already processed)
            if price not in self.lob:
                return False

            # Remove the order
            order = self.get_order(order_id, 'LMT', price)
            if type(order) != type(None):
                self.lob[price] = list(filter(lambda x: x.order_id != order_id, self.lob[price]))
                self.anonymised_lob[price] = list(filter(lambda x: x['order_id'] != order_id, self.anonymised_lob[price]))
                
                self.book_volume -= (order.qty - order.qty_filled) # Remove remainining liquidity

                # Remove the price if there is nothing available
                self.update_price(price)
                return True
            else:
                # Edge case (Order already processed)
                return False
        elif order_spec.order_type == 'MKT':
            order = self.get_order(order_id, 'MKT')

            if type(order) != type(None):
                self._market_order_q = list(filter(lambda x: x.order_id != order_id, self._market_order_q))
                self.anonymised_market_order_q = list(filter(lambda x: x['order_id'] != order_id, self.anonymised_market_order_q))
                self.recompute_stats()
                return True
            else:
                return False

        return False

    def has_market_orders(self):
        return len(self._market_order_q) > 0

    def recompute_stats(self):
        # Prices in ascending order
        available_prices = sorted(self.lob)

        # Compute best price
        # Note: If there is no current prices we leave it unchanged as the 'last' best price
        if len(available_prices) > 0:
            self.best_price = available_prices[-1] if self.book_side == 'bids' else available_prices[0]
        
        # compute num orders
        self.num_orders = sum([len(self.lob[price]) for price in self.lob]) + len(self._market_order_q)
        self.book_depth = len(available_prices)

    def update_price(self, price):
        if len(self.lob[price]) == 0:
            del(self.lob[price])
            del(self.anonymised_lob[price])

        self.recompute_stats()

    def update_best_quote(self, quote):
        if quote.order_type == "MKT":
            if quote.qty - quote.qty_filled > 0:
                # Update the quote
                self._market_order_q[0] = quote
                self.anonymised_market_order_q[0] = self.anonymise(quote)
            else:
                # Remove the quote if it is filled entirely
                self._market_order_q.pop(0)
                self.anonymised_market_order_q.pop(0)

            # Update the statistics of the halfbook
            self.recompute_stats() 
        elif quote.order_type == "LMT":
            increase_in_filled_qty = quote.qty_filled - self.lob[self.best_price][0].qty_filled

            if quote.qty - quote.qty_filled > 0:
                # Update the quote
                self.lob[self.best_price][0] = quote
                self.anonymised_lob[self.best_price][0] = self.anonymise(quote)
            else:
                # Remove the quote if it is filled entirely
                self.lob[self.best_price].pop(0)
                self.anonymised_lob[self.best_price].pop(0)
        
            # Remove the price if there is nothing available
            # And implicity recomputes the stats
        
            self.update_price(self.best_price)    

            # Remove the filled amount - Note we are only tracking limit volume
            # id %s qty %s filled %s incre %s vol %s
            self.book_volume -= increase_in_filled_qty
            assert(self.book_volume >= 0)

    def get_best_quote(self):
        """
        Gets the best available quote from the halfbook using the
        price time priority queue protocol.
        :return quote: an ExchangeOrder or None if none available
        """

        # Implements a price time priority queue
        has_limit_order = self.best_price in self.lob
        has_market_order = len(self._market_order_q) > 0

        if has_limit_order and has_market_order:
            best_limit_order = self.lob[self.best_price][0] 
            best_market_order = self._market_order_q[0]

            limit_arrived_before_market = best_limit_order.submission_time < best_market_order.submission_time

            if limit_arrived_before_market:
                return best_limit_order
            else:
                return best_market_order

        elif has_limit_order:
            return self.lob[self.best_price][0] 
        elif has_market_order:
            return self._market_order_q[0]
        else:
            return None

class LunaOrderbook: 
    def __init__(self, credentials, config, time_fn, ticker, tape, traders, observers, mark_traders_to_market, get_books, get_tape, update_pnls, trader_still_connected, get_trader_id):
        # TODO: Everything here is good we just need to configure the endpoint parameters for LUNA

        self._bids = LunaHalfOrderbook('bids')
        self._asks = LunaHalfOrderbook('asks')
        self.get_time = time_fn # Exchange time function
        self._ws_uri = 'wss://ws.luno.com/api/1/stream/' + ticker
        self.ticker = ticker
        self.credentials = credentials

        # Forwarded from exhcange
        self._tape = tape
        self._traders = traders
        self._observers = observers
        self.mark_traders_to_market = mark_traders_to_market
        self.get_books =  get_books
        self.get_tape = get_tape
        self.update_pnls = update_pnls
        self.trader_still_connected = trader_still_connected
        self.get_trader_id = get_trader_id
        self._credentials = credentials

    async def connect(self):
        while True: # For reconnection
            # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            # ssl_context.load_verify_locations(pathlib.Path("ssl_cert/cert.pem"))

            async with websockets.connect(self._ws_uri, ssl = True, max_size= None) as ws:
                await ws.send(json.dumps(self._credentials))
                self.build_book(json.loads(await ws.recv()))
                
                async def broadcast_to_trader_init(tid):
                     # Optimised to not send back everything
                    await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books()}))
                    await self._traders[tid].send(json.dumps({'type': 'tape', 'data': self.get_tape()}))

                await asyncio.gather(*[broadcast_to_trader_init(tid) for tid in self._traders])

                # Broadcast new book and tape to observers
                async def broadcast_to_observer_init(oid):
                    await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(order_type='LMT')}))
                    # Only observers may recieve the market book for debug purposes
                    await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(order_type='MKT')}))
                    await self._observers[oid].send(json.dumps({'type': 'tape', 'data': self.get_tape()}))

                await asyncio.gather(*[broadcast_to_observer_init(oid) for oid in self._observers])

                seq = -1

                while True:
                    updates = json.loads(await ws.recv())
                    
                    if type(updates) == type(" "):
                        continue

                    # Reconnect if out of sequence
                    if float(updates['sequence']) > seq:
                        break
                    else:
                        seq = float(updates['sequence'])

                        # Trade Updates
                        if updates['create_update']:
                            self.add_order(LunaToExchangeOrder(self.ticker, updates['create_update'], self.get_time(), self.get_trader_id))
                        if updates['delete_update']:
                            self.cancel_order_with_id(updates['delete_update']['order_id'])
                        if updates['trade_updates']:
                            latest_transactions = []

                            for trade_update in updates['trade_updates']:
                                # Internal Server Side Auction
                                transaction_pair, maker_order, taker_order = LunaToExchangeTransactionPair(self.ticker, updates['trade_update'], self.get_time(), self.get_order_by_id, self.get_trader_id)
                                
                                # Update Internal Order States
                                maker_order = update_named_tuple(maker_order, {'qty_filled': maker_order.qty_filled + transaction_pair.maker_transaction.qty_filled})
                                maker_order_hafbook = self._asks if maker_order.action == "SELL" else self._bids
                                maker_order_hafbook.update_best_quote(maker_order)

                                # Update taker_order (if it was also a limit order - we don't have access to the market book)
                                if taker_order.order_type == 'LMT': 
                                    taker_order = update_named_tuple(taker_order, {'qty_filled': taker_order.qty_filled + transaction_pair.maker_transaction.qty_filled})
                                    taker_order_hafbook = self._asks if taker_order.action == "SELL" else self._bids
                                    taker_order_hafbook.update_best_quote(taker_order)

                                # Perform Accounting Operations
                                # It makes sense to do them on the back end so we keep all the PnL Code for all traders in the one place
                                # Otherwise we need the backend to request from all traders and then pass from backend to frontend
                                # which is unecessary and more error prone and more prone to user meddling.
                                
                                # Note we make sure to update the pnls first and then notify the fills
                                # otherwise when we assert an order has been executed there will be a network delay
                                # in assessing risk which would lead to messy sleep statement workarounds
                                # Note all traders will have their pnl marked to market by this function
                                await self.update_pnls(transaction_pair)
                                maker_id, taker_id = transaction_pair.maker.tid, transaction_pair.taker.tid

                                # Distribute the transaction confirmations to the 2 parties
                                if self.trader_still_connected(maker_id):
                                    maker_ws = self._traders[maker_id]
                                    await maker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(transaction_pair.maker)}))

                                if self.trader_still_connected(taker_id):
                                    taker_ws = self._traders[taker_id]
                                    await taker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(transaction_pair.taker)}))

                                # Broadcast transaction to our traders
                                latest_transactions.append(transaction_pair)

                            self._tape += latest_transactions

                            # Broadcast new limit order books
                            async def broadcast_to_trader(tid):
                                # Optimised to not send back everything
                                await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker])}))
                                await self._traders[tid].send(json.dumps({'type': 'tape', 'data': self.get_tape(transactions = latest_transactions)}))

                            await asyncio.gather(*[broadcast_to_trader(tid) for tid in self._traders])

                            # Broadcast new book and tape to observers
                            async def broadcast_to_observer(oid):
                                await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker], order_type='LMT')}))
                                # Only observers may recieve the market book for debug purposes
                                await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(tickers = [self.ticker], order_type='MKT')}))
                                await self._observers[oid].send(json.dumps({'type': 'tape', 'data': self.get_tape(transactions = latest_transactions)}))

                            await asyncio.gather(*[broadcast_to_observer(oid) for oid in self._observers])

                            # We call mark to market again at to make sure 
                            # we have caught any no transacted market moving limits
                            await self.mark_traders_to_market(self.ticker)

    def build_book(self, book):
        for order_data in book['bids']:
            order_data_mod = {**order_data, 'type': 'BID'}
            self.add_order(LunaToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

        for order_data in book['asks']:
            order_data_mod = {**order_data, 'type': 'ASK'}
            self.add_order(LunaToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

    def add_order(self, exchange_order):
        halfbook = self._bids if exchange_order.action == "BUY" else self._asks
        halfbook.add_order(exchange_order)
    
    def get_order_by_id(self, order_id):
        buy_order = self._bids.get_order(order_id, 'LMT')

        if type(buy_order) == type(None):
            sell_order = self._asks.get_order(order_id, 'LMT')
            return sell_order
        else:
            return buy_order

    def cancel_order_with_id(self, order_id):
        buy_order = self._bids.get_order(order_id, 'LMT')
        
        if type(buy_order) != type(None):
            self._bids.cancel_order(buy_order)
        else:
            sell_order = self._asks.get_order(order_id, 'LMT')

            if type(sell_order) != type(None):
                self._asks.cancel_order(sell_order)
            else:
                warnings.warn('Order of type LMT is not a cancellable as it does not exist in the book', UserWarning)

    def cancel_order(self, order_spec):
        if order_spec.order_type == "LMT" or order_spec.order_type == "MKT":
            halfbook = self._bids if order_spec.action == "BUY" else self._asks
            return halfbook.cancel_order(order_spec)
        else:
            warnings.warn('Order of type [%s] is not a cancellable type' % order_spec.action, UserWarning)
            return False
    
    def get_LOB(self):
        return LOB(self._bids.anonymised_lob, self._asks.anonymised_lob, self._bids.best_price, self._asks.best_price, self._bids.book_depth, self._asks.book_depth, self._bids.num_orders, self._asks.num_orders, round(self._bids.book_volume,2), round(self._asks.book_volume,2))

    def get_market_book(self):
        return MarketBook(self._bids.anonymised_market_order_q, self._asks.anonymised_market_order_q)

class KrakenHalfOrderbook:
    def __init__(self, book_side):
        self.anonymised_lob = {}
        self.lob = {}

        self.book_side = book_side # bids or asks
        self.book_depth = 0 # Number of different prices
        self.num_orders = 0
        self.book_volume = 0 # Limit order book volume only
        self.best_price = 0
        self._market_order_q = []
        self.anonymised_market_order_q = []

    def anonymise(self, order):
        order_dict = dict(order._asdict())
        return dict(to_named_tuple(order_dict, ExchangeOrderAnon)._asdict())

    def update_orders(self, order):
        if order.order_type == "LMT":
            if order.price not in self.lob:
                self.book_volume += order.qty
            else:
                self.book_volume += order.qty - self.lob[order.price][0].qty

            # if qty for a price is 0, remove the price level from the book
            if order.qty == 0.0:
                self.lob.pop(order.price, None)
                self.anonymised_lob.pop(order.price, None)
            else:
                self.lob[order.price] = [order]
                self.anonymised_lob[order.price] = [self.anonymise(order)]
        else:
            if order.order_type == "MKT":
                warnings.warn('MKT order type is not supported for Kraken.', UserWarning)
            else:
                warnings.warn('An unknown order type [%s] was used and could not be executed' % order.action, UserWarning)

        self.recompute_stats()

    def get_order(self, order_id, order_type, price = -1):

        if order_type == 'LMT':
            if price > 0:
                order_match = list(filter(lambda x: x.order_id == order_id, self.lob[price]))
            else:
                all_orders = []
                for price in self.lob:
                    all_orders += self.lob[price]

                order_match = list(filter(lambda x: x.order_id == order_id, all_orders))
        else:
            order_match = list(filter(lambda x: x.order_id == order_id, self._market_order_q))

        return order_match[0] if len(order_match) > 0 else None

    def has_market_orders(self):
        return len(self._market_order_q) > 0

    def recompute_stats(self):
        # Prices in ascending order
        available_prices = sorted(self.lob)

        # Compute best price
        # Note: If there is no current prices we leave it unchanged as the 'last' best price
        if len(available_prices) > 0:
            self.best_price = available_prices[-1] if self.book_side == 'bids' else available_prices[0]
        
        # compute num orders
        self.num_orders = sum([len(self.lob[price]) for price in self.lob]) + len(self._market_order_q)
        self.book_depth = len(available_prices)

    def update_price(self, price):
        if len(self.lob[price]) == 0:
            del(self.lob[price])
            del(self.anonymised_lob[price])

        self.recompute_stats()

    def update_best_quote(self, quote):
        if quote.order_type == "MKT":
            warnings.warn(
                'MKT order type is not supported for Kraken.', UserWarning)
        elif quote.order_type == "LMT":
            increase_in_filled_qty = quote.qty_filled - self.lob[self.best_price][0].qty_filled

            if quote.qty - quote.qty_filled > 0:
                # Update the quote
                self.lob[self.best_price][0] = quote
                self.anonymised_lob[self.best_price][0] = self.anonymise(quote)
            else:
                # Remove the quote if it is filled entirely
                self.lob[self.best_price].pop(0)
                self.anonymised_lob[self.best_price].pop(0)
        
            # Remove the price if there is nothing available
            # And implicity recomputes the stats
        
            self.update_price(self.best_price)    

            # Remove the filled amount - Note we are only tracking limit volume
            # id %s qty %s filled %s incre %s vol %s
            self.book_volume -= increase_in_filled_qty
            assert(self.book_volume >= 0)

    def get_best_quote(self):
        """
        Gets the best available quote from the halfbook using the
        price time priority queue protocol.
        :return quote: an ExchangeOrder or None if none available
        """

        # Implements a price time priority queue
        has_limit_order = self.best_price in self.lob
        has_market_order = len(self._market_order_q) > 0

        if has_limit_order and has_market_order:
            best_limit_order = self.lob[self.best_price][0] 
            best_market_order = self._market_order_q[0]

            limit_arrived_before_market = best_limit_order.submission_time < best_market_order.submission_time

            if limit_arrived_before_market:
                return best_limit_order
            else:
                return best_market_order

        elif has_limit_order:
            return self.lob[self.best_price][0] 
        elif has_market_order:
            return self._market_order_q[0]
        else:
            return None

class KrakenOrderbook:
    def __init__(self, credentials, config, time_fn, ticker, tape, traders, observers, mark_traders_to_market, get_books, get_tape, update_pnls, trader_still_connected, get_trader_id):
        self._bids = KrakenHalfOrderbook('bids')
        self._asks = KrakenHalfOrderbook('asks')
        self.get_time = time_fn  # Exchange time function
        # since we do not trade on Kraken, we do not need to use wss://ws-auth.kraken.com
        self._ws_uri = 'wss://ws.kraken.com'
        self.ticker = ticker
        self.credentials = credentials

        # Forwarded from exhcange
        self._tape = tape
        self._traders = traders
        self._observers = observers
        self.mark_traders_to_market = mark_traders_to_market
        self.get_books =  get_books
        self.get_tape = get_tape
        self.update_pnls = update_pnls
        self.trader_still_connected = trader_still_connected
        self.get_trader_id = get_trader_id
        self._credentials = credentials

    async def connect(self):
        while True:
            async with websockets.connect(self._ws_uri, ssl = True, max_size= None) as ws:
                # initialization
                # get system status info
                system_status = json.loads(await ws.recv())
                assert system_status['event'] == 'systemStatus' and system_status['status'] == 'online', \
                    "Could not connect to the system. Response: " + str(system_status)

                # subscribe to book channel
                # get the maximum depth
                # the pair format is different than in Luno
                payload = {
                    "event": "subscribe",
                    "pair": [self.ticker[:3] + "/" + self.ticker[3:]],
                    "subscription": {
                        "name": "book",
                        "depth": 1000
                    }
                }
                await ws.send(json.dumps(payload))
                # we should get a confirmation about subscription
                subscription_status = json.loads(await ws.recv())
                assert subscription_status['status'] == "subscribed" and subscription_status['channelName'][:4] == "book", \
                    "Did not successfully subscribe to book channel. Response: " + \
                    str(subscription_status)
                
                # we should also get an initial snapshot of the book
                book_snapshot = json.loads(await ws.recv())
                book_channel_name = "book-" + str(payload["subscription"]["depth"])
                assert book_snapshot[2] == book_channel_name, \
                    "Did not receive expected book snapshot. Response: " + str(book_snapshot)
                self.build_book(book_snapshot)

                # broadcast the initial snapshot of the order book to the traders and observers
                async def broadcast_to_trader_init(tid):
                    # Optimised to not send back everything
                    await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books()}))
                    await self._traders[tid].send(json.dumps({'type': 'tape', 'data': self.get_tape()}))

                await asyncio.gather(*[broadcast_to_trader_init(tid) for tid in self._traders])

                # Broadcast new book and tape to observers
                async def broadcast_to_observer_init(oid):
                    await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(order_type='LMT')}))
                    # Only observers may recieve the market book for debug purposes
                    await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(order_type='MKT')}))
                    await self._observers[oid].send(json.dumps({'type': 'tape', 'data': self.get_tape()}))

                await asyncio.gather(*[broadcast_to_observer_init(oid) for oid in self._observers])

                # receive updates
                # we do not check for failures such as incorrect checksum or no heartbeat for some time
                # we return to the outer while loop if connection fails
                while True:
                    updates = json.loads(await ws.recv())

                    # make sure this is not a general message and that it relates to the book channel
                    if "event" not in updates and updates[2][:4] == "book":
                        # update the book
                        self.update_book(updates)

                        # Broadcast new limit order books
                        async def broadcast_to_trader(tid):
                            # Optimised to not send back everything
                            await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker])}))

                        await asyncio.gather(*[broadcast_to_trader(tid) for tid in self._traders])

                        # Broadcast new book and tape to observers
                        async def broadcast_to_observer(oid):
                            await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker], order_type='LMT')}))
                            # Only observers may recieve the market book for debug purposes
                            await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(tickers = [self.ticker], order_type='MKT')}))

                        await asyncio.gather(*[broadcast_to_observer(oid) for oid in self._observers])

                        # We call mark to market again at to make sure 
                        # we have caught any no transacted market moving limits
                        await self.mark_traders_to_market(self.ticker)

    def build_book(self, book_snapshot):
        # we could use the provided timestamp - but then it would be inconsistent with Luno, so use self.get_time()
        for order_data in book_snapshot[1]['bs']:
            # order_data is an array of price, volume, timestamp in this order
            # price is used as the id
            order_data_mod = {'id': order_data[0], 'type': 'BID', 'price': order_data[0], 'volume': order_data[1]}
            self.update_orders(KrakenToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

        for order_data in book_snapshot[1]['as']:
            # order_data is an array of price, volume, timestamp in this order
            # price is used as the id
            order_data_mod = {'id': order_data[0], 'type': 'ASK', 'price': order_data[0], 'volume': order_data[1]}
            self.update_orders(KrakenToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

    def update_orders(self, exchange_order):
        halfbook = self._bids if exchange_order.action == "BUY" else self._asks
        halfbook.update_orders(exchange_order)

    def update_book(self, updates):
        # some updates may be a republication - but that does not affect the result, so we do not check for it
        if "a" in updates[1]:
            for order_data in updates[1]['a']:
                order_data_mod = {'id': order_data[0], 'type': 'ASK', 'price': order_data[0], 'volume': order_data[1]}
                self.update_orders(KrakenToExchangeOrder(
                    self.ticker, order_data_mod, self.get_time(), self.get_trader_id))
        if "b" in updates[1]:
            for order_data in updates[1]['b']:
                order_data_mod = {'id': order_data[0], 'type': 'BID', 'price': order_data[0], 'volume': order_data[1]}
                self.update_orders(KrakenToExchangeOrder(
                    self.ticker, order_data_mod, self.get_time(), self.get_trader_id))
    
    def get_order_by_id(self, order_id):
        buy_order = self._bids.get_order(order_id, 'LMT')

        if type(buy_order) == type(None):
            sell_order = self._asks.get_order(order_id, 'LMT')
            return sell_order
        else:
            return buy_order

    def get_LOB(self):
        return LOB(self._bids.anonymised_lob, self._asks.anonymised_lob, self._bids.best_price, self._asks.best_price, self._bids.book_depth, self._asks.book_depth, self._bids.num_orders, self._asks.num_orders, round(self._bids.book_volume,2), round(self._asks.book_volume,2))

    def get_market_book(self):
        return MarketBook(self._bids.anonymised_market_order_q, self._asks.anonymised_market_order_q)

# This is only a temporary version to get a working market
class MarketDynamics:
    def __init__(self, traders, ticker, book, case_config, time_fn):
        self._case_config = case_config
        self._security_config = case_config['securities'][ticker]
        self._traders = traders
        self._ticker = ticker
        self._time_fn = time_fn
        self._step = 0
        self._tender_id = 0
        self._book = book # Book of the relevant security

        self._market_dynamics = self._security_config['market_dynamics']
        self._price_path = self._market_dynamics['price_path']
        self._tender_config = self._market_dynamics['institutional_orders']
        self._tenders_enabled = self._tender_config['enabled']
        
        # ------------ market parameters --------------
        self._midprice = self._security_config['starting_price']
        # What is the minium decimal places to display
        self._resolution = self._security_config['resolution']
        # How man times per second to update the market price 
        self._updates_per_second = self._price_path['updates_per_second']
        # The notional market time corresponding to a single price update
        self._notional_timestep = self._case_config['simulation_notional_timestep'] 
        # The sleep delay between steps
        self._step_price_delay = 1 / self._updates_per_second

        # Assuming 250 trading days per year
        trading_year_in_seconds = 60 * 60 * 24 * 250
        # Value of one step every _step_price_delay as a fraction of the trading year
        self._timestep = self._notional_timestep / trading_year_in_seconds
        # Annualised volatilty and expected returns
        self._expected_return = self._price_path['expected_return']
        self._volatility = self._price_path['volatility']

        # ------------- Tender Paramaters --------------------
        if self._tenders_enabled:
            # self._automated_trader_config = self._market_dynamics['automated_traders']
            # self._automated_traders = []

            # tender specification
            tenders_per_price_step = self._tender_config['avg_num_tenders_per_second'] / self._updates_per_second
            self._tender_rate = tenders_per_price_step
            self._expires_after = self._tender_config['expires_after']
            
            # Solve for gamma(a,b) given variance and b = 2
            mean = self._tender_config["tender_price_mean"]
            variance = self._tender_config["tender_price_deviation"]**2

            self._gamma_a, self._gamma_b = ((mean**2) / variance), (mean / variance)
            
            # Shift the distribution so quotes at undesirable prices are possible
            rv = gamma(self._gamma_a, scale = 1/self._gamma_b)
            self._gamma_shift = rv.ppf(self._tender_config['prob_of_bad_tender_price'])

            self._expected_tender_qty = self._tender_config["expected_tender_qty"]

    async def create_dynamics(self):
        await asyncio.sleep(0.5) # Allows the websocket server to become operational

        print("Creating Market Dynamics...")

        # if self._tenders_enabled:
        #     for traderType, count in self._automated_trader_config.items():
        #         if traderType == 'giveaway_trader':
        #             self._automated_traders += [GiveawayTrader() for i in range(0, count)]

        #     trader_activations = asyncio.gather(*[t.connect() for t in self._automated_traders])
        #     print("Activating automated traders...")
        #     await asyncio.gather(trader_activations, self.step_market_price_path())
        # else:
        #     await self.step_market_price_path()

        await self.step_market_price_path()

    async def step_market_price_path(self):
        while True:
            # TODO: This is a rather simple model of price we can introduce more variables
            # such as market shocks but this will do for now.

            # GBM Price Path
            drift = self._expected_return * self._timestep
            shock = self._volatility * normalvariate(0, 1) * np.sqrt(self._timestep)
            price_change = self._midprice * (drift + shock) # Price change is the shocked timestep return * current price
            self._midprice = self._midprice + price_change
        
            # Only do this once per second
            if self._tenders_enabled and self._step % self._updates_per_second == 0:
                await self.generate_tenders()
            
            await asyncio.sleep(self._step_price_delay)
            self._step += 1

    async def generate_tenders(self):
        tenders = []
        tids = [*self._traders]

        if len(tids) > 0:
            # Tenders simultaneously requested at a poisson rate
            num_tenders = poisson(lam=self._tender_rate)
            
            tenders += await asyncio.gather(*[self.create_tender(self._ticker, choice(['BUY', 'SELL']), self._traders[choice(tids)]) for tender in range(0,num_tenders)])

    @staticmethod
    def round_to_2_sf(x):
        return round(x, 1-int(floor(log10(abs(x)))))

    async def create_tender(self, ticker, action, trader):
        # Desired shape and expected value
        tender_qty = self.round_to_2_sf(self._expected_tender_qty * 3/2 * betavariate(3, 1.5))
        
        # Desired risk premium paid by the client
        improvement_on_best_quote = gammavariate(self._gamma_a, self._gamma_b)
        spread = self._book._asks.best_price - self._book._bids.best_price
        
        # If the action is BUY (we are buying from the client) so we
        # need to be able to sell at at a price >= midprice >= best bid

        if action == 'BUY':
            tender_price = (self._midprice - spread/2) - improvement_on_best_quote + self._gamma_shift
        else:
            tender_price = (self._midprice + spread/2) + improvement_on_best_quote - self._gamma_shift

        tender_price = round(tender_price, self._resolution)

        tender_order = TenderOrder(ticker, self.get_next_tender_id(), tender_qty, action, tender_price, self._time_fn() + self._expires_after)

        await trader.send(json.dumps({'type': 'tender', 'data': named_tuple_to_dict(tender_order)}))
        return tender_order
        # SEND TO TRADERS WHEN COMPUTED

    def get_next_tender_id(self):
        tender_id = 'tender_' + str(self._tender_id)
        self._tender_id += 1

        return tender_id

class Exchange:
    # TODO: Implement Risk Rules / trade limits
    def __init__(self, config_dir='./configs/backend_config.json'):
        # read config dir
        with open(config_dir) as config_file:
            self._config = json.load(config_file)
        
        self._exchange_name = self._config['exchanges']['active_case']
        self._case_config = self._config['exchanges'][self._exchange_name]

        if self._exchange_name == 'luno' or self._exchange_name == 'kraken':
            self._credentials = self._case_config['credentials']
            self._client = Client(api_key_id=self._credentials['api_key_id'], api_key_secret=self._credentials['api_key_secret'])

        
        self._port = self._config['websocket']['port']
        self._ip = self._config['websocket']['ip']
        self._webserver_port = self._config['app-websocket']['port']
        self._webserver_ip = self._config['app-websocket']['ip']
        self._traders = {}
        self._orders = {} # Maps orders to traders (Used by Luna)
        self._observers = {} # Front End Web Apps Observers
        self._pnls = {} # key is tid
        self._risk = {} # key is tid
        self._risk_limits = to_named_tuple(self._case_config['risk_limits'], RiskLimits)
        self._transaction_records = {} # key is tid
        self._suspect_trade_records = {} # key is tid
        self._tape = [] 
        self._initial_time = time.time()
        
        self._books = self.init_books()

        if self._exchange_name != 'luno' and self._exchange_name != 'kraken':
            self._market_dynamics = self.init_market_dynamics()

        self.setup_websocket_server()

    def setup_websocket_server(self):
        print("Initialising websocket...") 
        
        # Security
        # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # ssl_context.load_cert_chain(pathlib.Path("ssl_cert/cert.pem"))

        # Initialises the server and ensures it winds down gracefully
        loop = asyncio.get_event_loop()
        # log_slow_callbacks.enable(0.05) # Logs anything more than 100ms
        # handler = websockets.serve(self.exchange_handler, self._ip, self._port, ssl=ssl_context)
        
        # Backend Frontend Communications
        handler = websockets.serve(self.exchange_handler, self._ip, self._port, max_size = None)

        # Creating Price Paths for securities
        if self._exchange_name != 'luno' and self._exchange_name != 'kraken':
            dynamics = asyncio.gather(*[md.create_dynamics() for ticker, md in self._market_dynamics.items()])

        # Communications to web app intermediary
        # NOTE Lets disable the webserver and see if the bug persists...
        webserver = self.connect_to_web_server()

        # core = asyncio.gather(handler, dynamics)
        if self._exchange_name != 'luno' and self._exchange_name != 'kraken':
            core = asyncio.gather(webserver, handler, dynamics)
        elif self._exchange_name == 'kraken':
            book_monitors = asyncio.gather(*[book.connect() for ticker, book in self._books.items()])
            core = asyncio.gather(book_monitors, webserver)
            # do we want a handler here?
        else:
            book_monitors = asyncio.gather(*[book.connect() for ticker, book in self._books.items()])
            core = asyncio.gather(book_monitors, webserver, handler)

        server, _ = loop.run_until_complete(core)

        loop.run_forever()

        # Close the server
        server.close()
        loop.run_until_complete(server.wait_closed())

    async def connect_to_web_server(self):
        # Abstracts away messages sent to vuejs
        async with websockets.connect("ws://%s:%s/backend" % (self._webserver_ip, self._webserver_port), max_size= None) as ws:
            oid = self.get_trader_id_from_socket(ws)
            self._observers[oid] = ws

            try:
                print("Connected to vuejs middleware...")

                config_messages = [
                    {'type': 'LOBS', 'data': self.get_books()},
                    {'type': 'MBS', 'data': self.get_books(order_type='MKT')},
                    {'type': 'tape', 'data': self.get_tape()}
                ]

                setup_msg = {
                    'type':'config', 
                    'data':{
                        'oid': oid,
                        'exchange': self._config['exchanges'][self._exchange_name],
                        'exchange_open_time': self._initial_time
                    },
                    'n_config_messages': 1 + len(config_messages)
                }

                await ws.send(json.dumps(setup_msg)) # Send the trader their oid and exchange settings

                # Send initial messages required to render the viewport
                for msg in config_messages:
                    await ws.send(json.dumps(msg))

                while True:
                    # NOTE: This is probably not reccomended
                    await asyncio.sleep(1) # Holds the connection open
            except Exception as e:
                print(e)
                print("Closing connection with vuejs middleware...")
                del(self._observers[oid])
            finally:
                print("Closed connection with vuejs middleware...")
                # This will hopefully never be called but just to be clear
                
    async def exchange_handler(self, ws, path):
        # Paths
        # /observer (read only) Web socket gets registered to _observers
        # /traders both read and write gets registered to _observers
        
        is_trader = path == '/trader'

        # Register Trader
        if is_trader:
            tid = self.get_trader_id_from_socket(ws)
            self._traders[tid] = ws # The hash is now the trader id

            setup_msg = {
                'type':'config', 
                'data':{
                    'tid': tid,
                    'exchange': self._config['exchanges'][self._exchange_name],
                    'exchange_open_time': self._initial_time
                }
            }
        else:
            print("Socket path not recognised...")
            return # Unrecognised path

        try:
            if is_trader:
                # Give recently joined trder basic information required for setup
                await ws.send(json.dumps(setup_msg)) # Send the trader their tid and exchange settings
                await self.init_trader_account(tid) # Init the risk, pnl, transaction records amd transmit
                await ws.send(json.dumps({'type': 'LOBS', 'data': self.get_books()}))
                await ws.send(json.dumps({'type': 'tape', 'data': self.get_tape()}))
                await asyncio.gather(self.handle_msgs(ws), self.broadcast_active_traders(ws))
        finally:
            if is_trader:
                print("Connection with [%s] [%s] closed" % (('trader', tid)))
                del(self._traders[tid])
                await self.broadcast_active_traders(ws)
            else:
                print("Connection closed with unkown connection...")

    async def handle_msgs(self, ws):
        async for msg in ws:
            await self.route_msg(ws, msg)
            
    async def broadcast_current_time(self, ws):
        while True:
            await ws.send(json.dumps({'type': 'current_time', 'data': self.get_time()}))
            await asyncio.sleep(10)

    async def broadcast_active_traders(self, ws):
        for oid in self._observers:
            await self._observers[oid].send(json.dumps({'type': 'traders', 'data': list(self._traders.keys())}))

    async def route_msg(self, ws, msg):
        order_msg = json.loads(msg)
        
        s_type, data = order_msg['type'], order_msg['data']

        if s_type == 'add_order':
            order_spec = to_named_tuple(data, OrderSpec)
            
            if self.order_conforms_to_trader_risk_limits(order_spec): 

                book = self._books[order_spec.ticker]
                exchange_order = self.to_exchange_order(order_spec)

                if self._exchange_name == 'luna':
                    if order_spec.order_type == 'LMT':
                        # Lets say we use volume of 10GBP to buy BTC 
                        # Then the Amount of BTC we can buy is 10GBP / Price BTC
                        counter_volume = order_spec.qty / order_spec.price
                        res = self._client.post_limit_order(order_spec.ticker, order_spec.price, order_spec.action, counter_volume)
                        self._orders[res['order_id']] = order_spec.tid
                    else:
                        res = self._client.post_market_order(order_spec.ticker, order_spec.action, base_volume = order_spec.qty)
                        self._orders[res['order_id']] = order_spec.tid

                    await ws.send(json.dumps({'type': 'order_opened', 'data': named_tuple_to_dict(exchange_order)}))
                else:
                    book.add_order(exchange_order)

                    # Respond to user to confirm order dispatch
                    await ws.send(json.dumps({'type': 'order_opened', 'data': named_tuple_to_dict(exchange_order)}))
                    
                    # Recomputes the book / performs transactions where possible:
                    # Note this is necessary as it may provide additional liquidity to execute market orders
                    # which could not be previously executed and are queued.
                    transaction_pairs = book.auction()
                    latest_transactions = await self.process_new_transactions(ws, transaction_pairs)

                    # TODO : (LUNA)
                    # WE NEED TO AGAIN ENSURE THAT THE PROCESSING OF NEW TRANSACTIONS 
                    # IS HANDLED BY THE API 

                    self._tape += latest_transactions

                    # Broadcast new limit order books
                    async def broadcast_to_trader(tid):
                        # Optimised to not send back everything
                        await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [order_spec.ticker])}))
                        await self._traders[tid].send(json.dumps({'type': 'tape', 'data': self.get_tape(transactions = latest_transactions)}))

                    await asyncio.gather(*[broadcast_to_trader(tid) for tid in self._traders])

                    # Broadcast new book and tape to observers
                    async def broadcast_to_observer(oid):
                        await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [order_spec.ticker], order_type='LMT')}))
                        # Only observers may recieve the market book for debug purposes
                        await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(tickers = [order_spec.ticker], order_type='MKT')}))
                        await self._observers[oid].send(json.dumps({'type': 'tape', 'data': self.get_tape(transactions = latest_transactions)}))

                    await asyncio.gather(*[broadcast_to_observer(oid) for oid in self._observers])

                    # We call mark to market again at to make sure 
                    # we have caught any no transacted market moving limits
                    await self.mark_traders_to_market(order_spec.ticker)
            else:
                # Breaches risk limits
                await ws.send(json.dumps({'type': 'order_failed', 'data': data}))
    
        elif s_type == 'cancel_order':
            order_spec = to_named_tuple(data, OrderSpec)

            if self._exchange_name == 'luna':
                success = self._client.stop_order()['sucess']

                # Send to confirmation back to user
                await ws.send(json.dumps({'type': 'order_cancelled', 'data': {'order_spec': named_tuple_to_dict(order_spec), 'success': success}}))
            else:
                success = self._books[order_spec.ticker].cancel_order(order_spec)

                # Send to confirmation back to user
                await ws.send(json.dumps({'type': 'order_cancelled', 'data': {'order_spec': named_tuple_to_dict(order_spec), 'success': success}}))

                # TODO: Convert to efficient versions of below as above

                # Broadcast new limit order books
                for tid in self._traders:
                    await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books()}))

                # Broadcast new limit order books to observers
                for oid in self._observers:
                    await self._observers[oid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [order_spec.ticker])}))
                    await self._observers[oid].send(json.dumps({'type': 'MBS', 'data': self.get_books(tickers = [order_spec.ticker], order_type='MKT')}))

                # To catch any price movements due to cancellations
                await self.mark_traders_to_market(order_spec.ticker)

        elif s_type == 'accept_tender':
            tender_order = to_named_tuple(data, TenderOrder)
            
            if tender_order.expiration_time < self.get_time():
                # Tender Expired
                print("exchange - user out of sync delta : %s " % (self.get_time() - order_msg['exchange_time']))
                print("Real Lag between user send and server processing: %s " % (time.time() - order_msg['user_utc_time']))
                await ws.send(json.dumps({'type': 'tender_rejected', 'data': data}))
            else:
                # Emulate the tender for acounting using a transaction for pnl purposes
                tid = self.get_trader_id_from_socket(ws)

                await self.update_pnls_after_tender_accept(tid, tender_order)

                # Tender Ok
                await ws.send(json.dumps({'type': 'tender_fill', 'data': data}))

    def order_conforms_to_trader_risk_limits(self, order_spec):
        trader_risk = self._risk[order_spec.tid]
        multiplier = self._case_config['securities'][order_spec.ticker]['risk_limit_multiplier']
        weighted_qty = multiplier * order_spec.qty
        signed_qty = weighted_qty if order_spec.action == 'BUY' else -1 * weighted_qty
        
        security_positions = self._transaction_records[order_spec.tid][order_spec.ticker]
        security_net_pos = security_positions['BUY']['sum_qty'] - security_positions['SELL']['sum_qty']

        new_security_net_pos = security_net_pos + signed_qty
        gross_change = abs(new_security_net_pos) - abs(security_net_pos)

        is_within_net_limit = abs(trader_risk.net_position + signed_qty) < self._risk_limits.net_position
        is_within_gross_limit = abs(trader_risk.gross_position + gross_change) < self._risk_limits.gross_position

        return is_within_net_limit and is_within_gross_limit

    async def process_new_transactions(self, ws, transaction_pairs):
        latest_transactions = []

        for transaction_pair in transaction_pairs:
            maker_id, taker_id = transaction_pair.maker.tid, transaction_pair.taker.tid

            # Perform Accounting Operations
            # It makes sense to do them on the back end so we keep all the PnL Code for all traders in the one place
            # Otherwise we need the backend to request from all traders and then pass from backend to frontend
            # which is unecessary and more error prone and more prone to user meddling.
            
            # Note we make sure to update the pnls first and then notify the fills
            # otherwise when we assert an order has been executed there will be a network delay
            # in assessing risk which would lead to messy sleep statement workarounds
            # Note all traders will have their pnl marked to market by this function
            await self.update_pnls(transaction_pair)
            
            # Distribute the transaction confirmations to the 2 parties
            if self.trader_still_connected(maker_id):
                maker_ws = self._traders[maker_id]
                await maker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(transaction_pair.maker)}))

            if self.trader_still_connected(taker_id):
                taker_ws = self._traders[taker_id]
                await taker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(transaction_pair.taker)}))

            tape_transaction = TapeTransaction(transaction_pair.ticker, transaction_pair.action, transaction_pair.maker.qty, transaction_pair.maker.price, transaction_pair.timestamp)
            latest_transactions.append(tape_transaction)

        return latest_transactions
    
    def init_books(self):
        books = {}
        securities_config = self._config['exchanges'][self._exchange_name]['securities']

        for ticker in securities_config:
            print("Initialising book for ticker [%s] ..." % ticker)

            if self._exchange_name == 'luno':
                books[ticker] = LunaOrderbook(self._credentials, securities_config[ticker], 
                self.get_time, ticker, self._tape, self._traders, self._observers, self.mark_traders_to_market,  self.get_books, self.get_tape, self.update_pnls, self.trader_still_connected, self.get_trader_id)
            elif self._exchange_name == 'kraken':
                books[ticker] = KrakenOrderbook(self._credentials, securities_config[ticker], 
                self.get_time, ticker, self._tape, self._traders, self._observers, self.mark_traders_to_market,  self.get_books, self.get_tape, self.update_pnls, self.trader_still_connected, self.get_trader_id)
            else:
                books[ticker] = Orderbook(securities_config[ticker], time_fn=self.get_time)
        
        return books

    def init_market_dynamics(self):
        case_config = self._config['exchanges'][self._exchange_name]
        dynamics = {}

        for ticker in case_config['securities']:
            dynamics[ticker] = MarketDynamics(self._traders, ticker, self._books[ticker], case_config, time_fn=self.get_time)

        return dynamics

    async def init_trader_account(self, tid):
        """
        Initialises the trades pnl, risk and transaction records and transmits to the trader
        """
        print("Initialising Trader Account [%s]", tid)
        self._pnls[tid] = {} 
        # self._risk[tid] = TraderRisk(0,0,0,0,0,[])
        self._risk[tid] = TraderRisk(0,0,0,0,0)
        self._transaction_records[tid] = {}
        self._suspect_trade_records[tid] = [] 
        
        trader = self._traders[tid]
        await trader.send(json.dumps({'type':'risk', 'data': named_tuple_to_dict(self._risk[tid])}))

        for ticker in self._books:
            self._pnls[tid][ticker] = TickerPnL(ticker,0,0,0,0)
            await trader.send(json.dumps({'type':'pnl', 'data': named_tuple_to_dict(self._pnls[tid][ticker])}))
            
            # NOTE Right now i can't see any reason to need this for client to need this
            # it already has this in its own form that it needs
            self._transaction_records[tid][ticker] = {'BUY':{'sum_qty':0, 'sum_qty_price':0,'transactions':[]},'SELL':{'sum_qty':0, 'sum_qty_price':0,'transactions':[]}}
  
    async def update_pnls(self, transaction_pair):
        """
        Updates pnl, risk, transaction records for traders on both sides of the trade
        :param transaction_pair: of type TransactionPair
        """
        # action of the liquidity taker
        taker_action = transaction_pair.action
        maker_action = 'BUY' if taker_action == 'SELL' else 'SELL'
        
        if transaction_pair.maker.tid == transaction_pair.taker.tid:
            # Trading with oneself is a way to maniupalte realised + unrealised pnls
            # and is a suspect transaction
            # These transactions are irrelevant and misleading and thus reccorded and omitted from calculations
            self._suspect_trade_records[transaction_pair.maker.tid].append(transaction_pair)
        else:
            self.update_trader_transaction_record(transaction_pair.maker, maker_action, transaction_pair.ticker)
            self.update_trader_transaction_record(transaction_pair.taker, taker_action, transaction_pair.ticker)

        # Now update the pnl's of every trader to ensure mark to market
        # I've placed this here to ensure robust timely reporting
        await self.mark_traders_to_market(transaction_pair.ticker)

    async def update_pnls_after_tender_accept(self, tid, tender_order):
        current_time = self.get_time()
        tender_transaction = Transaction(tid, tender_order.tender_id, tender_order.qty, tender_order.price, current_time)
        self.update_trader_transaction_record(tender_transaction, tender_order.action, tender_order.ticker)
        await self.recompute_trader_pnl(tid, tender_order.ticker)

    async def mark_traders_to_market(self, ticker):
        await asyncio.gather(*[self.recompute_trader_pnl(tid, ticker) for tid in self._traders if tid >= 0])

    def update_trader_transaction_record(self, transaction, action, ticker):
        """
        Updates trade risk, pnl and transaction records
        :param transaction: A trader's transaction of type Transaction
        :param action: Either BUY or SELL
        :param ticker: A security ticker string
        """
        tid = transaction.tid

        if tid == -1:
            return

        # Allocate the transaction so we can trace it later and perform computations
        trader_record = self._transaction_records[tid]
        ticker_record = trader_record[ticker]
        side_record = ticker_record[action] # Buy or sell transaction record
        transactions = side_record['transactions']

        transactions.append(transaction)

        # Saves on expensive computations later in recompute_trader_pnl
        side_record['sum_qty'] += transaction.qty
        side_record['sum_qty_price'] += transaction.qty * transaction.price

    async def recompute_trader_pnl(self, tid, ticker):
        """
        Recomputes the PNL and Risk metrics and notifies the trader of the change
        :param tid: a trader id
        """
        trader_record = self._transaction_records[tid]
        ticker_record = trader_record[ticker]

        # Now let us recompute the pnl
        exchange_config = self._config['exchanges'][self._exchange_name]
        securities_config = exchange_config['securities']
        contract_config = securities_config[ticker]
        contract_point_value = contract_config['contract_point_value']
        contract_currency = contract_config['quote_currency']
        base_currency = exchange_config['base_currency']

        best_bid, best_ask = self._books[ticker]._bids.best_price, self._books[ticker]._asks.best_price, 

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
        conversion = 1 if base_currency == contract_currency else self._books[contract_currency]._bids.best_price
       
        unrealised_pnl_base_currency = unrealised_pnl_contract_currency * conversion
        realised_pnl_base_currency = realised_pnl_contract_currency * conversion
        pnl_total_base_currency = total_pnl_contract_currency * conversion

        # PnL history by ticker
        current_time = self.get_time()
        trader_pnls = self._pnls[tid]
        # ticker_pnl_history = trader_pnls[ticker].total_pnl_history
        # ticker_pnl_history.append({'time':current_time,'value':pnl_total_base_currency})

        # NOTE We remove history objects as it was becoming v expensive to keep encoding and sending
        # these to the clients many many times!

        # Update ticker pnl
        # trader_pnls[ticker] = TickerPnL(ticker, net_position, unrealised_pnl_base_currency, realised_pnl_base_currency, pnl_total_base_currency, ticker_pnl_history)

        trader_pnls[ticker] = TickerPnL(ticker, net_position, unrealised_pnl_base_currency, realised_pnl_base_currency, pnl_total_base_currency)

        # Recompute risk
        trader_risk = self._risk[tid]

        overall_net_position = sum([pnl.net_position for ticker, pnl in trader_pnls.items()])
        overall_gross_position = sum([abs(pnl.net_position) for ticker, pnl in trader_pnls.items()])
        overall_unrealised = sum([pnl.unrealised for ticker, pnl in trader_pnls.items()])
        overall_realised = sum([pnl.realised for ticker, pnl in trader_pnls.items()])
        overall_pnl = sum([pnl.total_pnl for ticker, pnl in trader_pnls.items()])

        # pnl_history = trader_risk.pnl_history
        # # We avoid deeply nesting named tuples as this can be painful for data transfer
        # pnl_history.append({'time':current_time,'value':overall_pnl})
        
        # self._risk[tid] = TraderRisk(overall_net_position, overall_gross_position,overall_unrealised, overall_realised, overall_pnl, pnl_history)

        self._risk[tid] = TraderRisk(overall_net_position, overall_gross_position,overall_unrealised, overall_realised, overall_pnl)

        # TODO: Compute SHARPE, CALMAR, SORTINO, etc

        # send trader their updated pnl and risk
        trader = self._traders[tid]
        await trader.send(json.dumps({'type':'pnl', 'data': named_tuple_to_dict(trader_pnls[ticker])}))
        await trader.send(json.dumps({'type':'risk', 'data': named_tuple_to_dict(self._risk[tid])}))

    def to_exchange_order(self, order_spec):
        """
        Converts an OrderSpec object submitted by a user to an exchange order and timestamps the submission
        """
        order = dict(order_spec._asdict())
        order['qty_filled'] = 0
        order['submission_time'] = self.get_time()

        return to_named_tuple(order, ExchangeOrder)

    def get_time(self):
        """
        Gets the current time in seconds
        :return time in seconds since exchange opened:
        """
        return time.time() - self._initial_time

    def get_books(self, tickers = None, order_type='LMT'):
        """
        :param tickers: If specified only books for these tickers will be returned
        :return books in json format
        """
        if order_type == 'LMT':
            if type(tickers) == type(None):
                return {ticker: dict(self._books[ticker].get_LOB()._asdict()) for ticker in self._books}
            else:
                return {ticker: dict(self._books[ticker].get_LOB()._asdict()) for ticker in self._books if ticker in tickers}
        elif order_type == 'MKT':
            if type(tickers) == type(None):
                return {ticker: dict(self._books[ticker].get_market_book()._asdict()) for ticker in self._books}
            else:
                return {ticker: dict(self._books[ticker].get_market_book()._asdict()) for ticker in self._books if ticker in tickers}
        else:
            return None

    def get_tape(self, transactions = None):
        """
        :param transactions: If specified only these transactions will be returned
        :return tape in json format
        """
        if type(transactions) == type(None):
            return [dict(tape_transaction._asdict()) for tape_transaction in self._tape]
        else:
            return [dict(tape_transaction._asdict()) for tape_transaction in transactions]

    def get_trader_id_from_socket(self, ws):
        return hash(ws)

    def trader_still_connected(self, tid):
        return tid in self._traders

    def get_trader_id(self, order_id):
        if order_id in self._orders:
            return self._orders[order_id]
        else:
            return -1
                

"""
Starts the server!
"""
exchange = Exchange() 
