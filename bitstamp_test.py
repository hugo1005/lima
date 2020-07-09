import websockets
import asyncio
import json

import requests

_ws_uri = 'wss://ws.bitstamp.net'

class BitstampOrderbook:
    def __init__(self, credentials, config, time_fn, ticker, tape, traders, observers, mark_traders_to_market, get_books, get_tape, update_pnls, trader_still_connected, get_trader_id, db):
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
        self.db = db

    async def connect(self):
        res = requests.get('https://www.bitstamp.net/api/v2/order_book/'+ self.ticker + '?group=1')
        data = res.json()
        
        self.build_book(data)
        self.db.update_prices(self.get_books(order_type='LMT'), "kraken")

        while True:
            async with websockets.connect(self._ws_uri, ssl = True, max_size= None) as ws:
                await ws.send(json.dumps({"event":"bts:subscribe", "data": {
                    "channel": "diff_order_book_" + self.ticker
                }}))

                assert json.loads(await ws.recv())['event'] == 'bts:subscription_succeeded'
                seq = -1

                async for data in ws:
                    parsed = json.loads(data)
                    
                    if 'event' in parsed:
                        if parsed['event'] == "bts:request_reconnect":
                            break

                    update = parsed['data']
                    timestamp = float(update['timestamp'])
                    microtimestamp = float(update['microtimestamp'])
                    asks = update['asks']
                    bids = update['bids']

                    if microtimestamp < seq:
                        print("-------- OUT OF SEQUENCE (RESTARTING) -----------")
                        break

                    seq = microtimestamp

                    for bid in bids:
                        price = float(bid[0])
                        qty = float(bid[1])
                        order_data_mod = {'order_id': price, 'type': 'BID', 'price': price, 'volume': qty}
                        
                        self.update_orders(KrakenToExchangeOrder(
                            self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

                    for ask in asks:
                        price = float(ask[0])
                        qty = float(ask[1])
                        order_data_mod = {'order_id': price, 'type': 'BID', 'price': price, 'volume': qty}
                        
                        self.update_orders(KrakenToExchangeOrder(
                            self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

                    self.db.update_prices(self.get_books(order_type='LMT'), "kraken")
                # print(timestamp, asks, bids)

    def build_book(self, book_snapshot):
        # we could use the provided timestamp - but then it would be inconsistent with Luno, so use self.get_time()
        for order_data in book_snapshot['bids']:
            # order_data is an array of price, volume, timestamp in this order
            # price is used as the id
            price = float(order_data[0])
            qty = float(order_data[1])
            order_data_mod = {'order_id': price, 'type': 'BID', 'price': price, 'volume': qty}
            self.update_orders(KrakenToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

        for order_data in book_snapshot['asks']:
            # order_data is an array of price, volume, timestamp in this order
            # price is used as the id
            price = float(order_data[0])
            qty = float(order_data[1])
            order_data_mod = {'order_id': price, 'type': 'ASK', 'price': price, 'volume': qty}
            self.update_orders(KrakenToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

    def update_orders(self, exchange_order):
        halfbook = self._bids if exchange_order.action == "BUY" else self._asks
        halfbook.update_orders(exchange_order)

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

loop = asyncio.get_event_loop()
loop.run_until_complete(connect())