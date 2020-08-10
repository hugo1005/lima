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
from simulation_orderbooks import HalfOrderbook, Orderbook

from exchange_sockets import BitstampOrderbook, GlobitexOrderbook, KrakenOrderbook, LunoOrderbook

from aiodebug import log_slow_callbacks
import logging
import argparse
import requests
import traceback

class Exchange:
    # TODO: Implement Risk Rules / trade limits
    def __init__(self, exchange_name, db, orderbook_class, config_dir='./configs/backend_config.json'):
        # read config dir
        with open(config_dir) as config_file:
            self._config = json.load(config_file)
        
        # self._exchange_name = self._config['exchanges']['active_case']
        self._exchange_name = exchange_name
        self._case_config = self._config['exchanges'][self._exchange_name]

        if self._exchange_name != 'simulator':
            self._credentials = self._case_config['credentials']
        
        self.orderbook_class = orderbook_class
        self._port = self._case_config['websocket']['port']
        self._ip = self._case_config['websocket']['ip']
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
        self._db = db

    def connect(self):
        if self._exchange_name == 'simulator':
            self._market_dynamics = self.init_market_dynamics()
        
        self._books = self.init_books()
        return self.setup_websocket_server()

    async def setup_websocket_server(self):
        print("Initialising websocket...") 
        # Backend Frontend Communications
        handler = websockets.serve(self.exchange_handler, self._ip, self._port, max_size = None)
        
        # Creating Price Paths for securities
        if self._exchange_name == 'simulator':
            dynamics = asyncio.gather(*[md.create_dynamics() for ticker, md in self._market_dynamics.items()])

        # Communications to web app intermediary
        # NOTE Lets disable the webserver and see if the bug persists...
        # webserver = self.connect_to_web_server()

        # core = asyncio.gather(handler, dynamics)
        if self._exchange_name == 'simulator':
            core = asyncio.gather(handler, dynamics)
        else:
            book_monitors = asyncio.gather(*[book.connect() for ticker, book in self._books.items()])
            core = asyncio.gather(book_monitors, handler)
        
        return core

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
                        'exchange_open_time': self._initial_time,
                        'exchange_name': self._exchange_name
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
        except:
            print("Connection closed due to error!")
            error = sys.exc_info()
            print(error)
            traceback.print_exc()
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

                if self._exchange_name != 'simulator':
                    book = self._books[order_spec.ticker]
                    order_id = book.new_order(order_spec)
                    self._orders[order_id] = order_spec
                    print(self._orders)

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

            if self._exchange_name != 'simulator':
                book = self._books[order_spec.ticker]
                success = book.revoke_order(order_spec)

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

            # if self._exchange_name == 'luno':
            #     books[ticker] = LunoOrderbook(self._credentials, securities_config[ticker], 
            #     self.get_time, ticker, self._tape, self._traders, self._observers, self.mark_traders_to_market,  self.get_books, self.get_tape, self.update_pnls, self.trader_still_connected, self.get_trader_id, self._db)
            if self._exchange_name != 'simulator':
                books[ticker] = self.orderbook_class(self.create_exchange_config_for_orderbook(), ticker, self._credentials, True, exchange_name=self._exchange_name)
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
        
        if transaction_pair.maker.tid == transaction_pair.taker.tid and transaction_pair.maker.tid != -1:
            # Trading with oneself is a way to maniupalte realised + unrealised pnls
            # and is a suspect transaction
            # These transactions are irrelevant and misleading and thus reccorded and omitted from calculations
            self._suspect_trade_records[transaction_pair.maker.tid].append(transaction_pair)
        else:
            if transaction_pair.maker.tid != -1:
                self.update_trader_transaction_record(transaction_pair.maker, maker_action, transaction_pair.ticker)
            if transaction_pair.taker.tid != -1:
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
            return self._orders[order_id].tid
        else:
            return -1

    def get_internal_order_id(self, order_id):
        if order_id in self._orders:
            return self._orders[order_id].order_id
        else:
            return -1
                
    def create_exchange_config_for_orderbook(self):
        return {
            'time_fn': self.get_time,
            'tape':  self._tape,
            'traders':  self._traders,
            'observers': self._observers,
            'mark_traders_to_market': self.mark_traders_to_market,
            'get_books': self.get_books,
            'get_tape': self.get_tape,
            'update_pnls': self.update_pnls,
            'trader_still_connected': self.trader_still_connected,
            'get_trader_id': self.get_trader_id,
            'get_internal_order_id': self.get_internal_order_id,
            'db': self._db,
        }

def main():
    parser = argparse.ArgumentParser(description='Runs algo backtest on secuirties')
    parser.add_argument("-e","--exchanges", nargs='+' ,help="exchanges to run")
    args = parser.parse_args()

    with Database() as db:
        exchanges_dict = {
            'luno': Exchange('luno',db, LunoOrderbook),
            'bitstamp':Exchange('bitstamp',db, BitstampOrderbook),
            'globitex':Exchange('globitex',db, GlobitexOrderbook),
            'kraken':Exchange('kraken',db, KrakenOrderbook)
        }
        
        exchanges = [exchanges_dict[exc] for exc in args.exchanges]
        
        loop = asyncio.get_event_loop()
        core = asyncio.gather(*[exchange.connect() for exchange in exchanges])

        servers = loop.run_until_complete(core)
        loop.run_forever()

        for server in servers:
            servers[0].close()
        
        loop.run_until_complete(asyncio.gather(*[server[0].wait_closed() for server in servers]))

if __name__ == "__main__":
    main()
