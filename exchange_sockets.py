import sys
import websockets
import requests
import time
import asyncio
import json
from collections import namedtuple
from shared import to_named_tuple, ExchangeOrder, MarketBook, ExchangeOrderAnon, LOB, named_tuple_to_dict, TransactionPair, Transaction,update_named_tuple, TapeTransaction
from abc import ABC, abstractmethod
import traceback
import warnings


from tornado.websocket import websocket_connect

from luno_python.client import Client
import bitstamp.client as BitstampClient

class ExternalHalfOrderbook:
    def __init__(self, book_side):
        # Propertieis
        self.anonymised_lob = {}
        self.lob = {}
        self.book_side = book_side # bids or asks
        
        # Updateable stats
        self.book_depth = 0 # Number of different prices
        self.num_orders = 0
        self.book_volume = 0 # Limit order book volume only
        self.best_price = 0

    def anonymise(self, order):
        order_dict = dict(order._asdict())
        return dict(to_named_tuple(order_dict, ExchangeOrderAnon)._asdict())

    def add_order(self, order):
        """
        Adds the limit order to the book
        """
        if order.price in self.lob:
            existing_idx = self.get_order_idx(order)
            
            if type(existing_idx) != type(None):
                self.cancel_order(self.lob[order.price][existing_idx])

            if order.price in self.lob:
                self.add_order_at_existing_price(order)
            else:
                self.add_order_at_new_price(order)
        else:
            self.add_order_at_new_price(order)

    def add_order_at_existing_price(self,order):
        self.lob[order.price].append(order)
        self.anonymised_lob[order.price].append(self.anonymise(order))
        # Update Stats (Special)
        self.num_orders += 1
        self.book_volume += order.qty
        self.best_price = max(list(self.lob.keys())) if self.book_side == 'bids' else min(list(self.lob.keys()))
    
    def add_order_at_new_price(self,order):
        self.lob[order.price] = [order]
        self.anonymised_lob[order.price] = [self.anonymise(order)]
        # Update Stats (Special)
        self.book_depth += 1
        self.num_orders += 1
        self.book_volume += order.qty
        self.best_price = max(list(self.lob.keys())) if self.book_side == 'bids' else min(list(self.lob.keys()))

    def get_order(self, order_id, order_type, price = -1):
        """
        Finds the limit order in the book
        """

        if price > 0:
            idx = self.get_order_idx_by_id(order_id, price)
            
            if type(idx) != type(None):
                return self.lob[price][idx]
        else:
            for price_level in self.lob:
                idx = self.get_order_idx_by_id(order_id, price_level)

                if type(idx) != type(None):
                    return self.lob[price_level][idx]

        return None

    def cancel_order(self, order, idx=-1):
        """
        Removes the order from the book.
        """
        if idx >= 0:
            self.cancel_order_at_idx(order, idx)
        else:
            idx = self.get_order_idx(order)
            
            if type(idx) != type(None):
                self.cancel_order_at_idx(order, idx)
            else:
                print("Warning... Order could not be found to be cancelled")
    
    def get_order_idx(self, order):
        return self.get_order_idx_by_id(order.order_id, order.price)

    def get_order_idx_by_id(self, order_id, price):
        for idx, existing in enumerate(self.lob[price]):
            if existing.order_id == order_id:
                return idx

        return None

    def cancel_order_at_idx(self, order, idx):
        self.lob[order.price].pop(idx)
        self.anonymised_lob[order.price].pop(idx)

        if len(self.lob[order.price]) == 0:
            del(self.lob[order.price])
            del(self.anonymised_lob[order.price])

            self.book_depth -= 1
        
        self.num_orders -= 1
        self.book_volume -= order.qty
        self.best_price = max(list(self.lob.keys())) if self.book_side == 'bids' else min(list(self.lob.keys()))  

    def get_best_quote(self):
        """
        Gets the best available quote from the halfbook using the
        price time priority queue protocol.
        :return quote: an ExchangeOrder or None if none available
        """
        return self.lob[self.best_price][0]

    def get_anonymised_lob(self, limit=10):
        sorted_prices_iter = sorted(self.lob.keys())
        prices = list(sorted_prices_iter) if self.book_side == 'asks' else list(reversed(sorted_prices_iter))

        top_prices = prices[:min(limit, len(prices)-1)]
        minified_lob = {}

        for price in top_prices:
            minified_lob[price] = self.anonymised_lob[price]

        return minified_lob
   
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
        
        # Internal Order Tracking
        self._client_orders = {}

        # User Defined in Subclass
        self._ws_uri = self.define_websocket_url()
        self.handlers = self.define_handler_mapping()
        self._subscription_message = self.define_subscription_message()
        self._trade_subscription_message = self.define_trade_subscription_message()
        self._book_snapshot_uri = self.define_book_snapshot_uri()

    """ Standardised Connection Methods """
    async def connect(self):
        while True: # For reconnection
            await self.safely_recieve_data()

    async def safely_recieve_data(self):
        try:
            await self.recieve_data()
        except:
            print("Rebooting %s connection due to connection closure!" % self.exchange_name )
            
            error = sys.exc_info()
            print(error)
            traceback.print_exc()
            time.sleep(10) # Wait for connection to be resetablished

    async def recieve_data(self):
        self.reinitialise_half_books()
        self.build_book_snapshot()
        self.update_database()
        await asyncio.gather(self.incremental_updates(), self.trade_updates())
    
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
        ws = await websocket_connect(self._ws_uri)
        await self.send_credentials(ws)
        await self.assert_setup_success(ws)
        
        if self._subscription_message:
            await self.subscribe_to_stream(ws, self._subscription_message)
        
        await self.send_snapshot_to_traders()

        seq = -1

        while True:
            msg = await ws.read_message()
            if msg is None: break
            seq = await self.parse_incremental_update(msg, seq)

    async def trade_updates(self):
        if type(self._trade_subscription_message) != None:
            ws = await websocket_connect(self._ws_uri)

            await self.assert_setup_success(ws)

        
            await self.subscribe_to_stream(ws, self._trade_subscription_message), 
            
            seq = -1

            while True:
                msg = await ws.read_message()
                if msg is None: break
                seq = await self.parse_trade_update(msg, seq)

    async def subscribe_to_stream(self, ws, sub_msg):
        if type(self._subscription_message) != type(None):
            await ws.write_message(sub_msg)
            
            if self._has_subscription_success_response:
                await self.assert_subscription_success(ws)

    async def send_snapshot_to_traders(self):
        await asyncio.gather(*[self.broadcast_to_trader(tid) for tid in self._traders])

    async def broadcast_to_trader(self, tid):
        # Optimised to not send back everything
        book = json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker])})
        await self._traders[tid].send(book)

    async def handle_event(self, event_type, parsed, seq):
        handler = self.handlers[event_type]
        new_seq = handler(parsed, seq)
        await self.propogate_event_updates()
        
        return new_seq

    async def propogate_event_updates(self):
        await self.send_snapshot_to_traders()
        self.update_database()
        # await self.mark_traders_to_market(self.ticker)

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
        return LOB(self._bids.get_anonymised_lob(), self._asks.get_anonymised_lob(), self._bids.best_price, self._asks.best_price, self._bids.book_depth, self._asks.book_depth, self._bids.num_orders, self._asks.num_orders, round(self._bids.book_volume,2), round(self._asks.book_volume,2))

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

    async def update_traders_with_transactions(self, maker, taker, qty, use_external_order_id = True):
        internal_taker_order_id = self.get_internal_order_id(taker.order_id) if use_external_order_id else taker.order_id
        internal_maker_order_id = self.get_internal_order_id(maker.order_id) if use_external_order_id else maker.order_id

        taker_transaction = Transaction(taker.tid, internal_taker_order_id, qty, taker.price, time.time())
        maker_transaction = Transaction(maker.tid, internal_maker_order_id, qty, maker.price, time.time())
        transaction_pair = TransactionPair(self.ticker, taker.action, maker_transaction, taker_transaction, self.get_time())
                    
        if self.trader_still_connected(maker.tid):
            maker_ws = self._traders[maker.tid]
            await maker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(maker_transaction)}))
    
        if self.trader_still_connected(taker.tid):
            taker_ws = self._traders[taker.tid]
            await taker_ws.send(json.dumps({'type': 'order_fill', 'data': named_tuple_to_dict(taker_transaction)}))

        # Similarly we need some way to deal with None Types here (and replciate to other exchange implementations)
        await self.update_pnls(transaction_pair)

        tape_transaction = TapeTransaction(self.ticker, taker.action, qty, taker.price, taker_transaction.timestamp)
        self._tape += [tape_transaction]

        # await self.mark_traders_to_market(self.ticker)
        
        latest_tape_data = json.dumps({'type': 'tape', 'data': self.get_tape()})
        for tid in self._traders:
            if self.trader_still_connected(tid):
                await self._traders[tid].send(latest_tape_data)

    def get_internal_order_id(self, external_order_id):

        if external_order_id in self._client_orders:
            return self._client_orders[external_order_id].order_id
        else:
            return -1

    def get_external_order_id(self, internal_order_id):
        print("Looking for internal id: ",internal_order_id," in: ", self._client_orders)
        for external_order_id in self._client_orders:
            if self._client_orders[external_order_id].order_id == internal_order_id:
                return external_order_id
        else:
            return None

    def new_order(self, order_spec):
        """:returns order_id"""
        internal_order_id = order_spec.order_id
        external_order_id = self.post_order(order_spec)
        internal_order_representation = ExchangeOrder(self.ticker, order_spec.tid, internal_order_id, order_spec.order_type, order_spec.qty, order_spec.action, order_spec.price, 0, time.time())

        self._client_orders[external_order_id] = internal_order_representation
        return external_order_id

    @abstractmethod
    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        # return  'wss://ws.bitstamp.net'
        print("Warning: Unimplemeneted!")
        pass
    
    @abstractmethod
    async def send_credentials(self, ws):
        """
        Send any necessary credentials to the server
        """
        print("Warning! Not implemented")

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
    def define_trade_subscription_message(self):
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

    @abstractmethod
    async def parse_trade_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest trade
        """
        print("Warning: Unimplemeneted!")
        # parsed = json.loads(msg)
        # event_type = parsed['event']
        # data = parsed['data']

        # return self.map_message_to_handler(event_type, data, seq)

    @abstractmethod
    def post_order(self, order_spec):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

    def revoke_order(self, order_spec):
        """:returns order_id"""
        external_order_id = self.get_external_order_id(order_spec.order_id)

        if type(external_order_id) != type(None):
            return self.revoke_order_from_sever(external_order_id)
        else:
            print("Warning: order could not be found to be revoked!")
            return False

    @abstractmethod
    def revoke_order_from_sever(self, order_id):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

class BitstampOrderbook(ExternalOrderbook):
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='bitstamp'):
        super().__init__(exchange_config, ticker, credentials, await_success_response, exchange_name=exchange_name)
        self._client = BitstampClient.Trading(username=credentials['username'], key=credentials['key'], secret=credentials['secret'])

    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        return None

    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        return  'wss://ws.bitstamp.net'

    async def send_credentials(self, ws):
        """
        Send any necessary credentials to the server
        """
        return None

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
    
    def define_trade_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        return json.dumps({
            "event":"bts:subscribe", 
            "data": {"channel": "live_trades_" + self.ticker}
        })

    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        return 'https://www.bitstamp.net/api/v2/order_book/'+ self.ticker + '?group=2'

    async def assert_subscription_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        response = await ws.read_message()
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

    async def parse_trade_update(self, msg, seq):
        """ 
        MODIFY: Each exchange may have a slightly different JSON structure
        :return seq: The sequence number of the latest trade
        """
        parsed = json.loads(msg)
        trade = parsed['data']

        # Provided
        qty = trade['amount']
        price = trade['price']
        buy_oid = trade['buy_order_id']
        sell_oid = trade['sell_order_id']
        direction = 'BUY' if trade['type'] == 0 else 'SELL'

        # Implied
        buy_order_type = 'MKT' if direction == 'BUY' else 'LMT'
        sell_order_type = 'LMT' if direction == 'BUY' else 'MKT'
        seller_tid = self.get_trader_id(sell_oid)
        buyer_tid = self.get_trader_id(buy_oid)

        buy_order = ExchangeOrder(self.ticker, buyer_tid, buy_oid, buy_order_type, qty, 'BUY', price, qty, self.get_time())
        sell_order = ExchangeOrder(self.ticker, seller_tid, sell_oid, sell_order_type, qty, 'SELL', price, qty, self.get_time())
        
        taker = buy_order if buy_order.order_type == 'MKT' else sell_order
        maker = buy_order if buy_order.order_type == 'LMT' else sell_order
        
        await self.update_traders_with_transactions(maker, taker, qty)

    def post_order(self, order_spec):
        """:returns order_id"""
        base = order_spec.ticker[0:3]
        quote = order_spec.ticker[3:]
        if order_spec.action == 'BUY':
            if order_spec.order_type == 'LMT':
                print(order_spec)
                res = self._client.buy_limit_order(order_spec.qty, order_spec.price, base=base, quote=quote)
            else:
                res = self._client.buy_market_order(order_spec.qty, base=base, quote=quote)
        else:
            if order_spec.order_type == 'LMT':
                print(order_spec)
                res = self._client.sell_limit_order(order_spec.qty, order_spec.price, base=base, quote=quote)
            else:
                res = self._client.sell_market_order(order_spec.qty, base=base, quote=quote)

        return int(res['id'])

    def revoke_order_from_sever(self, order_id):
        """:returns order_id"""
        try:
            self._client.cancel_order(order_id)
            return True
        except:
            print("Warning order could not be cancelled on bitstamp")
            return False

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

    async def send_credentials(self, ws):
        """
        Send any necessary credentials to the server
        """
        return None

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

    def post_order(self, order_spec):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

    def revoke_order_from_sever(self, order_id):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

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
        system_status = json.loads(await ws.read_message())
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
        subscription_status = json.loads(await ws.read_message())
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

    def post_order(self, order_spec):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

    def revoke_order_from_sever(self, order_id):
        """:returns order_id"""
        print("Warning Uimplemented: Post Order")

class LunoOrderbook(ExternalOrderbook):
    def __init__(self, exchange_config, ticker, credentials, await_success_response, exchange_name='bitstamp'):
        super().__init__(exchange_config, ticker, credentials, await_success_response, exchange_name=exchange_name)
        self._client = Client(api_key_id=credentials['api_key_id'], api_key_secret=credentials['api_key_secret'])

    async def assert_setup_success(self, ws):
        """ MODIFY: Assert that stream was succesfully subscribed """
        return None

    def define_websocket_url(self):
        """ MODIFY: define the enpoint for the websocket
        """
        return  'wss://ws.luno.com/api/1/stream/' + self.ticker

    async def send_credentials(self, ws):
        """
        Send any necessary credentials to the server
        """
        await ws.write_message(json.dumps(self.credentials))

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
    
    def define_trade_subscription_message(self):
        """ MODIFY: Define message (in string format) for subscription request"""
        return None

    def define_book_snapshot_uri(self):
        """ MODIFY: Define snapshot endpoint """
        return 'https://api.luno.com/api/1/orderbook_top?pair='+ self.ticker

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
        price, qty, order_id = float(order_msg['price']), float(order_msg['volume']), order_msg['price']

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
        price, qty = float(order_msg['price']), float(order_msg['volume'])
        order_id, order_type =  order_msg['order_id'], order_msg['type']

        # inferred
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
        is_snapshot = 'asks' in parsed
        is_string = type(parsed) == type(" ")
        if not is_snapshot and not is_string:
            create_data = parsed['create_update']
            cancel_data = parsed['delete_update']
            trade_data = parsed['trade_updates']
            
            if type(trade_data) == type(None):
                trade_data = []

            seq = float(parsed['sequence'])

            if type(cancel_data) != type(None):
                # Occurs when an order is cancelled

                event_type = 'order_deleted'
                cancel_data['microtimestamp'] = seq
                return await self.map_message_to_handler(event_type, cancel_data, seq)

            elif type(create_data) != type(None) and len(trade_data) == 0:
                # Occurs when a new LMT order is created

                event_type = 'order_created'
                create_data['microtimestamp'] = seq
                return await self.map_message_to_handler(event_type, create_data, seq)

            elif type(create_data) != type(None) and len(trade_data) > 0:
                # Occurs when a created LMT order is immediately filled

                event_type = 'order_changed'
                create_data['microtimestamp'] = seq
                new_seq = await self.map_message_to_handler(event_type, create_data, seq)

                for trade in trade_data:
                    maker_oid = trade['maker_order_id']
                    taker_oid = trade['taker_order_id']
                    qty = float(trade['base'])

                    maker = self._client_orders[maker_oid] if maker_oid in self._client_orders else None
                    taker = self._client_orders[taker_oid] if taker_oid in self._client_orders else None
                    print(maker_oid, taker_oid)
                    if type(maker) == type(None) and type(taker) == type(None):
                        continue
                    else:
                        if type(taker) == type(None):
                            inv_order_type = 'LMT' if maker.order_type == 'MKT' else 'MKT'
                            inv_action = 'BUY' if maker.action == 'SELL' else 'SELL'
                            taker = ExchangeOrder(self.ticker, -1, taker_oid, inv_order_type, qty, inv_action, maker.price, qty, maker.submission_time)
                        elif type(maker) == type(None):
                            inv_order_type = 'LMT' if taker.order_type == 'MKT' else 'MKT'
                            inv_action = 'BUY' if taker.action == 'SELL' else 'SELL'
                            maker = ExchangeOrder(self.ticker, -1, maker_oid, inv_order_type, qty, inv_action, taker.price, qty, taker.submission_time)
                        
                        await self.update_traders_with_transactions(maker, taker, qty, use_external_order_id=False)

                return new_seq
            elif type(create_data) == type(None) and len(trade_data) > 0:
                # Occurs when an order is updated by several trades

                for trade in trade_data:
                    maker_oid = trade['maker_order_id']
                    taker_oid = trade['taker_order_id']
                    qty = float(trade['base'])
                    print('trade_only: ',maker_oid, taker_oid)
                    # Modify the orders in the book
                    # Compute the new order state
                    # Call the order changed event
                    new_maker_order = self.update_order_with_fill(maker_oid, qty)
                    new_taker_order = self.update_order_with_fill(taker_oid, qty)

                    if type(new_maker_order) != type(None):
                        self.cancel_order_with_id(maker_oid)
                        self.add_order(new_maker_order)
                    
                    if type(new_taker_order) != type(None):
                        self.cancel_order_with_id(taker_oid)
                        self.add_order(new_taker_order)

                    # Notify our trading clients of the changes
                    maker = self._client_orders[maker_oid] if maker_oid in self._client_orders else None
                    taker = self._client_orders[taker_oid] if taker_oid in self._client_orders else None
                    print(maker_oid, taker_oid)
                    if type(maker) == type(None) and type(taker) == type(None):
                        continue
                    else:
                        if type(taker) == type(None):
                            inv_order_type = 'LMT' if maker.order_type == 'MKT' else 'MKT'
                            inv_action = 'BUY' if maker.action == 'SELL' else 'SELL'
                            taker = ExchangeOrder(self.ticker, -1, taker_oid, inv_order_type, qty, inv_action, maker.price, qty, maker.submission_time)
                        elif type(maker) == type(None):
                            inv_order_type = 'LMT' if taker.order_type == 'MKT' else 'MKT'
                            inv_action = 'BUY' if taker.action == 'SELL' else 'SELL'
                            maker = ExchangeOrder(self.ticker, -1, maker_oid, inv_order_type, qty, inv_action, taker.price, qty, taker.submission_time)
                        
                        await self.update_traders_with_transactions(maker, taker, qty, use_external_order_id=False)

    def update_order_with_fill(self, order_id, qty):
        order = self.get_order_by_id(order_id)

        if type(order) != type(None):
            return update_named_tuple(order, {'qty':order.qty - qty})
        else:
            return None

    # Overriden Method
    def handle_order_delete(self, data, seq):
        new_seq = self.assert_sequence_integrity(data, seq)
        self.cancel_order_with_id(data['order_id'])
        return new_seq

    async def parse_trade_update(self, msg, seq):
        return None

    def post_order(self, order_spec):
        """:returns order_id"""
        print("Posting order:", order_spec)
        if order_spec.order_type == 'LMT':
            print(order_spec)
            order_action = 'BID' if  order_spec.action == 'BUY' else 'ASK'
            res = self._client.post_limit_order(order_spec.ticker, order_spec.price, order_action, order_spec.qty)
        else:
            if order_spec.action == 'BUY':
                ask_price = round(self._asks.best_price,2) # best bid
                counter_volume = order_spec.qty * ask_price # How much euro to purchase order_spec.qty in BTC
                print(counter_volume)
                res = self._client.post_market_order(order_spec.ticker, order_spec.action, counter_volume = round(counter_volume,2))
            else:
                res = self._client.post_market_order(order_spec.ticker, order_spec.action, base_volume = round(order_spec.qty,4))

        return res['order_id']
    
    def revoke_order_from_sever(self, order_id):
        """:returns order_id"""
        res = self._client.stop_order(order_id)
        return res['success']
