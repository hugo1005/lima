import sys
import websockets
import requests
import time
import asyncio
import json
from collections import namedtuple
from shared import to_named_tuple, ExchangeOrder, MarketBook, ExchangeOrderAnon, LOB
from abc import ABC, abstractmethod
import traceback
import warnings

class ExternalHalfOrderbook:
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

class ExternalOrderbook(ABC): 
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='luno'):
        # Stanardised info passed from backend
        # exchange_config = {
        #     'time_fn': None,
        #     'tape': None,
        #     'traders': None,
        #     'observers': None,
        #     'mark_traders_to_market': None,
        #     'get_books': None,
        #     'get_tape': None,
        #     'update_pnls': None,
        #     'trader_still_connected': None,
        #     'get_trader_id': None,
        #     'db': None,
        # }
        super().__init__()

        # Backend Params
        self.get_time = exchange_config['time_fn']
        self._tape = exchange_config['tape']
        self._traders = exchange_config['traders']
        self._observers = exchange_config['observers']
        self.mark_traders_to_market = exchange_config['mark_traders_to_market']
        self.get_books =  exchange_config['get_books']
        self.get_tape = exchange_config['get_tape']
        self.update_pnls = exchange_config['update_pnls'] 
        self.trader_still_connected =  exchange_config['trader_still_connected'] 
        self.get_trader_id = exchange_config['get_trader_id'] 
        self.db = exchange_config['db'] 
        self.exchange_name = exchange_name

        # Args
        self.ticker = ticker
        self.credentials = credentials
        self._has_subscription_success_response = await_success_response
        
        # User Defined in Subclass
        self._ws_uri = self.define_websocket_url()
        self.handlers = self.define_handler_mapping()
        self._subscription_message = self.define_subscription_message()
        self._book_snapshot_uri = self.define_book_snapshot_uri()

    """ Standardised Connection Methods """
    async def connect(self):
        while True: # For reconnection
            await self.safely_recieve_data()

    async def safely_recieve_data(self):
        try:
            await self.recieve_data()
        except:
            print("Rebooting connection due to connection closure!")
            error = sys.exc_info()
            print(error)
            traceback.print_exc()
            time.sleep(10) # Wait for connection to be resetablished

    async def recieve_data(self):
        self.reinitialise_half_books()
        self.build_book_snapshot()
        self.update_database()
        await self.incremental_updates()
    
    def reinitialise_half_books(self):
        self._bids = ExternalHalfOrderbook('bids')
        self._asks = ExternalHalfOrderbook('asks')

    def build_book_snapshot(self):
        res = requests.get(self._book_snapshot_uri)
        data = res.json()
        self.build_book(data)
    
    def extract_from_dict(self, data, target):
        if target in data:
            return data[target]
        elif 'result' in data:
            nested = data['result']
            return nested[list(nested.keys())[0]][target]
        else:
            return []

    def update_database(self):
        self.db.update_prices(self.get_books(tickers = [self.ticker], order_type='LMT'), self.exchange_name)

    def build_book(self, book):
        bids = self.extract_from_dict(book, 'bids')
        asks = self.extract_from_dict(book, 'asks')

        for bid in bids:
            order = self.parse_snapshot_order(bid, 'BID')
            self.add_order(order)
            
        for ask in asks:
            order = self.parse_snapshot_order(ask, 'ASK')
            self.add_order(order)

    async def incremental_updates(self):
        async with websockets.connect(self._ws_uri, ssl = True, max_size= None) as ws:
            await self.assert_setup_success(ws)
            await self.subscribe_to_stream(ws)
            await self.send_snapshot_to_traders()

            seq = -1

            async for msg in ws:
                seq = await self.parse_incremental_update(msg, seq)

    async def subscribe_to_stream(self, ws):
        if type(self._subscription_message) != type(None):
            await ws.send(self._subscription_message)
            
            if self._has_subscription_success_response:
                await self.assert_subscription_success(ws)

    async def send_snapshot_to_traders(self):
        await asyncio.gather(*[self.broadcast_to_trader(tid) for tid in self._traders])

    async def broadcast_to_trader(self, tid):
        # Optimised to not send back everything
        book = json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker])})
        await self._traders[tid].send(book)

        # tape = json.dumps({'type': 'tape', 'data': self.get_tape()})
        # await self._traders[tid].send(tape)

    async def handle_event(self, event_type, parsed, seq):
        handler = self.handlers[event_type]
        new_seq = handler(parsed, seq)
        await self.propogate_event_updates()
        
        return new_seq

    async def propogate_event_updates(self):
        await self.send_snapshot_to_traders()
        self.update_database()
        await self.mark_traders_to_market(self.ticker)

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

    def handle_order_change(self, data, seq):
        # A neat trick :) its  a hack we will fix this eventually
        self.handle_order_delete(data, seq)
        self.handle_order_create(data, seq)

        return seq
    
    def handle_order_create(self, data, seq):
        new_seq = self.assert_sequence_integrity(data, seq)
        order = self.parse_streamed_order(data)
        self.add_order(order)
        return new_seq

    def handle_order_delete(self, data, seq):
        new_seq = self.assert_sequence_integrity(data, seq)

        order = self.parse_streamed_order(data)
        self.cancel_order_with_id(order.order_id)
        return new_seq

    def handle_reconnect_request(self, parsed, seq):
        raise ConnectionResetError("Exchange requests reconnect...")
 
    async def map_message_to_handler(self, event_type, data, seq):
        if event_type in self.handlers:
            return await self.handle_event(event_type, data, seq)
        else:
            print("Unkown event occured.... %s" % event_type)
            return seq

    @abstractmethod
    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        # return  'wss://ws.bitstamp.net'
        print("Warning: Unimplemeneted!")
        pass

    @abstractmethod
    def define_handler_mapping(self):
        """ MODIFY: Define the mapping between handlers and internal required methods 
        [handle_reconnect_request, self.handle_order_create, self.handle_order_delete, self.handle_order_change]
        """
        # return {
        #     "bts:request_reconnect": self.handle_reconnect_request,
        #     "order_created": self.handle_order_create,
        #     "order_deleted": self.handle_order_delete,
        #     "order_changed": self.handle_order_change,
        # }
        print("Warning: Unimplemeneted!")
        pass

    @abstractmethod
    def define_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        # return json.dumps({
        #     "event":"bts:subscribe", 
        #     "data": {"channel": "live_orders_" + self.ticker}
        # })
        pass

    @abstractmethod
    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        print("Warning: Unimplemeneted!")
        # return 'https://www.bitstamp.net/api/v2/order_book/'+ self.ticker + '?group=2'
        pass

    @abstractmethod
    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        print("Warning: Unimplemeneted!")
        # response = await ws.recv()
        # assert json.loads(response)['event'] == 'bts:subscription_succeeded'

    @abstractmethod
    async def assert_subscription_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        print("Warning: Unimplemeneted!")
        # response = await ws.recv()
        # assert json.loads(response)['event'] == 'bts:subscription_succeeded'

    @abstractmethod
    def assert_sequence_integrity(self, data, seq):
        """ MODIFY: Assert that stream sequencing of messages is correct """
        print("Warning: Unimplemeneted!")
        # new_seq = float(data['microtimestamp'])

        # if new_seq < seq:
        #     raise ValueError("Exchange requests reconnect, message out of sequence...")
        # else:
        #     return new_seq
        
    @abstractmethod
    def parse_snapshot_order(self, order_msg, side):
        """ 
        MODIFY: Format of order data recieved in initial snapshot 
        :return ExchangeOrder
        """
        print("Warning: Unimplemeneted!")
        # # provided
        # price, qty, order_id = float(order_msg[0]), float(order_msg[1]), order_msg[2]

        # # inferred
        # action = 'BUY' if side == 'BID' else 'SELL'
        # tid = self.get_trader_id(order_id)
        # qty_filled = 0
        # submission_time = self.get_time()

        # return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, qty_filled, submission_time)

    @abstractmethod
    def parse_streamed_order(self, order_msg):
        """ 
        MODIFY: Format of order data recieved in stream data 
        :return ExchangeOrder: An order as specified in shared.py
        """
        print("Warning: Unimplemeneted!")
        # # provided
        # price, qty = float(order_msg['price']), float(order_msg['amount'])
        # order_id, order_type =  order_msg['id'], int(order_msg['order_type'])

        # # inferred
        # action = 'BUY' if order_type == 0 else 'SELL'
        # tid = self.get_trader_id(order_id)
        # submission_time = self.get_time()

        # return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, 0, submission_time)

    @abstractmethod
    async def parse_incremental_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest order
        """
        print("Warning: Unimplemeneted!")
        # parsed = json.loads(msg)
        # event_type = parsed['event']
        # data = parsed['data']

        # return self.map_message_to_handler(event_type, data, seq)

class BitstampOrderbook(ExternalOrderbook):
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='bitstamp'):
        super().__init__(exchange_config, ticker, credentials, await_success_response, exchange_name=exchange_name)
    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        return None

    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        return  'wss://ws.bitstamp.net'

    def define_handler_mapping(self):
        """ MODIFY: Define the mapping between handlers and internal required methods 
        [handle_reconnect_request, self.handle_order_create, self.handle_order_delete, self.handle_order_change]
        """
        return {
            "bts:request_reconnect": self.handle_reconnect_request,
            "order_created": self.handle_order_create,
            "order_deleted": self.handle_order_delete,
            "order_changed": self.handle_order_change,
        }

    def define_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        return json.dumps({
            "event":"bts:subscribe", 
            "data": {"channel": "live_orders_" + self.ticker}
        })

    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        return 'https://www.bitstamp.net/api/v2/order_book/'+ self.ticker + '?group=2'

    async def assert_subscription_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        response = await ws.recv()
        assert json.loads(response)['event'] == 'bts:subscription_succeeded'

    def assert_sequence_integrity(self, data, seq):
        """ MODIFY: Assert that stream sequencing of messages is correct """
        new_seq = float(data['microtimestamp'])

        if new_seq < seq:
            raise ValueError("Exchange requests reconnect, message out of sequence...")
        else:
            return new_seq
        
    def parse_snapshot_order(self, order_msg, side):
        """ 
        MODIFY: Format of order data recieved in initial snapshot 
        :return ExchangeOrder
        """
        # provided
        price, qty, order_id = float(order_msg[0]), float(order_msg[1]), order_msg[2]

        # inferred
        action = 'BUY' if side == 'BID' else 'SELL'
        tid = self.get_trader_id(order_id)
        qty_filled = 0
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, qty_filled, submission_time)

    def parse_streamed_order(self, order_msg):
        """ 
        MODIFY: Format of order data recieved in stream data 
        :return ExchangeOrder: An order as specified in shared.py
        """
        # provided
        price, qty = float(order_msg['price']), float(order_msg['amount'])
        order_id, order_type =  order_msg['id'], int(order_msg['order_type'])

        # inferred
        action = 'BUY' if order_type == 0 else 'SELL'
        tid = self.get_trader_id(order_id)
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, 0, submission_time)

    async def parse_incremental_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest order
        """
        parsed = json.loads(msg)
        event_type = parsed['event'].strip()
        data = parsed['data']
        return await self.map_message_to_handler(event_type, data, seq)

class GlobitexOrderbook(ExternalOrderbook):
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='globitex'):
        super().__init__(exchange_config, ticker, credentials, await_success_response)

    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        return None

    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        return  'wss://stream.globitex.com/market-data'

    def define_handler_mapping(self):
        """ MODIFY: Define the mapping between handlers and internal required methods 
        [handle_reconnect_request, self.handle_order_create, self.handle_order_delete, self.handle_order_change]
        """
        return {
            "bts:request_reconnect": self.handle_reconnect_request,
            "order_created": self.handle_order_create,
            "order_deleted": self.handle_order_delete,
            "order_changed": self.handle_order_change,
        }

    def define_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        return None

    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        return 'https://api.globitex.com/api/1/public/orderbook/'+ self.ticker

    async def assert_subscription_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        return None

    def assert_sequence_integrity(self, data, seq):
        """ MODIFY: Assert that stream sequencing of messages is correct """
        new_seq = float(data['microtimestamp'])

        if new_seq < seq:
            raise ValueError("Exchange requests reconnect, message out of sequence...")
        else:
            return new_seq
        
    def parse_snapshot_order(self, order_msg, side):
        """ 
        MODIFY: Format of order data recieved in initial snapshot 
        :return ExchangeOrder
        """
        # provided
        price, qty = float(order_msg[0]), float(order_msg[1])

        # inferred
        order_id = price
        action = 'BUY' if side == 'BID' else 'SELL'
        tid = self.get_trader_id(order_id)
        qty_filled = 0
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, qty_filled, submission_time)

    def parse_streamed_order(self, order_msg):
        """ 
        MODIFY: Format of order data recieved in stream data 
        :return ExchangeOrder: An order as specified in shared.py
        """
        # provided
        price, qty, order_type = float(order_msg['price']), float(order_msg['size']), order_msg['order_type']
    
        # inferredter
        order_id = price
        action = 'BUY' if order_type == 0 else 'SELL'
        tid = self.get_trader_id(order_id)
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, 0, submission_time)

    async def parse_incremental_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest order
        """
        parsed = json.loads(msg)

        if "MarketDataIncrementalRefresh" in parsed:
            data = parsed['MarketDataIncrementalRefresh']

            if data["symbol"] == self.ticker:
                current_seq = data["seqNo"]
                
                for side in ['bid', 'ask']:
                    for order_data in data[side]:
                        order_data['microtimestamp'] = current_seq
                        order_data['order_type'] = side
                        
                        order = self.parse_streamed_order(order_data)

                        if order.qty == 0:
                            return await self.map_message_to_handler("order_deleted", order_data, current_seq)
                        else:
                            halfbook = self._bids if side == 'bid' else self._asks
                            
                            if order.price in halfbook.lob:
                                return await self.map_message_to_handler("order_changed", order_data, current_seq)
                            else: 
                                return await self.map_message_to_handler("order_created", order_data, current_seq)
            else:
                return seq
        else:
            return seq

class KrakenOrderbook(ExternalOrderbook):
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='kraken'):
        super().__init__(exchange_config, ticker, credentials, await_success_response, exchange_name=exchange_name)

    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        return  'wss://ws.kraken.com'

    def define_handler_mapping(self):
        """ MODIFY: Define the mapping between handlers and internal required methods 
        [handle_reconnect_request, self.handle_order_create, self.handle_order_delete, self.handle_order_change]
        """
        return {
            "bts:request_reconnect": self.handle_reconnect_request,
            "order_created": self.handle_order_create,
            "order_deleted": self.handle_order_delete,
            "order_changed": self.handle_order_change,
        }

    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        system_status = json.loads(await ws.recv())
        assert system_status['event'] == 'systemStatus' and system_status['status'] == 'online', \
            "Could not connect to the system. Response: " + str(system_status)

    def define_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        payload = json.dumps({
            "event": "subscribe",
            "pair": [self.ticker[:3] + "/" + self.ticker[3:]],
            "subscription": {
                "name": "book",
                "depth": 1000
            }
        })

        return payload

    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        return 'https://api.kraken.com/0/public/Depth?pair=' + self.ticker +'&count=100'

    async def assert_subscription_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        subscription_status = json.loads(await ws.recv())
        assert subscription_status['status'] == "subscribed" and subscription_status['channelName'][:4] == "book", \
                        "Did not successfully subscribe to book channel. Response: " + \
                        str(subscription_status)

    def assert_sequence_integrity(self, data, seq):
        """ MODIFY: Assert that stream sequencing of messages is correct """
        return True
        
    def parse_snapshot_order(self, order_msg, side):
        """ 
        MODIFY: Format of order data recieved in initial snapshot 
        :return ExchangeOrder
        """
        # provided
        price, qty = float(order_msg[0]), float(order_msg[1])

        # inferred
        order_id = price
        action = 'BUY' if side == 'BID' else 'SELL'
        tid = self.get_trader_id(order_id)
        qty_filled = 0
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, qty_filled, submission_time)

    def parse_streamed_order(self, order_msg):
        """ 
        MODIFY: Format of order data recieved in stream data 
        :return ExchangeOrder: An order as specified in shared.py
        """
        # provided
        price, qty, order_type = float(order_msg[0]), float(order_msg[1]), order_msg[3]
    
        # inferredter
        order_id = price
        action = 'BUY' if order_type == 'BID' else 'SELL'
        tid = self.get_trader_id(order_id)
        submission_time = self.get_time()

        return ExchangeOrder(self.ticker, tid, order_id, 'LMT', qty, action, price, 0, submission_time)

    async def parse_incremental_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest order
        """
    
        parsed = json.loads(msg)

        if len(parsed) == 4:
            data = parsed[1]
            for side in ['b', 'a']:
                if side in data:
                    for order_data in data[side]:
                        order_data.append('BID' if side == 'b' else 'ASK')
                        timestamp = order_data[2]
                        
                        order = self.parse_streamed_order(order_data)

                        if order.qty == 0:
                            return await self.map_message_to_handler("order_deleted", order_data, timestamp)
                        else:
                            halfbook = self._bids if side == 'b' else self._asks
                            
                            if order.price in halfbook.lob:
                                return await self.map_message_to_handler("order_changed", order_data, timestamp)
                            else: 
                                return await self.map_message_to_handler("order_created", order_data, timestamp)
        
        return -1 # We don't have seq info for Kraken


