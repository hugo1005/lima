class BitstampOrderbook: 
    def __init__(self, credentials, config, time_fn, ticker, tape, traders, observers, mark_traders_to_market, get_books, get_tape, update_pnls, trader_still_connected, get_trader_id, db):
        # TODO: Everything here is good we just need to configure the endpoint parameters for LUNA
        self.get_time = time_fn # Exchange time function
        self._ws_uri = 'wss://ws.bitstamp.net'
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
        while True: # For reconnection
            try:
                # ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                # ssl_context.load_verify_locations(pathlib.Path("ssl_cert/cert.pem"))
                self._bids = LunaHalfOrderbook('bids')
                self._asks = LunaHalfOrderbook('asks')
                
                res = requests.get('https://www.bitstamp.net/api/v2/order_book/'+ self.ticker + '?group=2')
                data = res.json()
                self.build_book(data)
                self.db.update_prices(self.get_books(tickers = [self.ticker], order_type='LMT'), "bitstamp")

                async with websockets.connect(self._ws_uri, ssl = True, max_size= None) as ws:
                    await ws.send(json.dumps({"event":"bts:subscribe", "data": {
                        "channel": "diff_order_book_" + self.ticker
                    }}))
                    
                    assert json.loads(await ws.recv())['event'] == 'bts:subscription_succeeded'
    
                    async def broadcast_to_trader_init(tid):
                        # Optimised to not send back everything
                        await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books()}))
                        # await self._traders[tid].send(json.dumps({'type': 'tape', 'data': self.get_tape()}))

                    await asyncio.gather(*[broadcast_to_trader_init(tid) for tid in self._traders])

                    seq = -1

                    while True:
                        parsed = json.loads(await ws.recv())
                        
                        if 'event' in parsed:
                            if parsed['event'] == "bts:request_reconnect":
                                print("Reconnecting to bitstamp...")
                                break
                            elif parsed['event'] == "order_created":
                                if parsed['data']['microtimestamp'] < seq:
                                    break

                                self.add_order(BitstampToExchangeOrderV2(self.ticker, parsed['data'], self.get_time(), self.get_trader_id))
                                seq = parsed['data']['microtimestamp'] 
                                
                            elif parsed['event'] == "order_deleted":
                                self.cancel_order_with_id(parsed['data']['id'])
                            else:
                                print("Unkown event occured.... %s" % parsed['event'])

                            if parsed['event'] == "order_created" or parsed['event'] == "order_deleted":
                                
                                # Broadcast new limit order books
                                async def broadcast_to_trader(tid):
                                    # Optimised to not send back everything
                                    await self._traders[tid].send(json.dumps({'type': 'LOBS', 'data': self.get_books(tickers = [self.ticker])}))

                                await asyncio.gather(*[broadcast_to_trader(tid) for tid in self._traders])

                                self.db.update_prices(self.get_books(tickers = [self.ticker], order_type='LMT'), "bitstamp")

                                # We call mark to market again at to make sure 
                                # we have caught any no transacted market moving limits
                                await self.mark_traders_to_market(self.ticker)
            except:
                print("Rebooting connection due to unexpected closure!")
                print(sys.exc_info())
                time.sleep(10) # Wait for connection to be resetablished


    def build_book(self, book):
        for order_data in book['bids']:
            price = float(bid[0])
            qty = float(bid[1])
            order_id = bid[2]
            order_data_mod = {'order_id':order_id, 'price':price, 'qty':qty , 'type': 'BID'}

            self.add_order(BitstampToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

        for order_data in book['asks']:
            price = float(ask[0])
            qty = float(ask[1])
            order_id = ask[2]
            order_data_mod = {'order_id':order_id, 'price':price, 'qty':qty , 'type': 'BID'}

            self.add_order(BitstampToExchangeOrder(self.ticker, order_data_mod, self.get_time(), self.get_trader_id))

    """ This is all independent of what exchange we use""""

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
