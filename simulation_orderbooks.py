import numpy as np
import asyncio
import websockets
import json
import ssl
import sys
import pathlib
import warnings
import time
from luno_python.client import Client
from random import normalvariate, gammavariate, betavariate, choice
from numpy.random import poisson
from scipy.stats import gamma
from math import log10, floor

from database import Database
from shared import LOB, OrderSpec, ExchangeOrder, Transaction, TransactionPair, ExchangeOrderAnon, TapeTransaction, MarketBook, TickerPnL, TraderRisk, TenderOrder, RiskLimits
from shared import to_named_tuple, update_named_tuple, named_tuple_to_dict, LunaToExchangeOrder, LunaToExchangeTransactionPair, KrakenToExchangeOrder, BitstampToExchangeOrder, BitstampToExchangeOrderV2
# from traders import GiveawayTrader

from exchange_sockets import BitstampOrderbook, GlobitexOrderbook, KrakenOrderbook, LunoOrderbook

from aiodebug import log_slow_callbacks
import logging
import argparse
import requests
import traceback

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
