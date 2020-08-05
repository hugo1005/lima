from frontend import Security, ExchangeConnection
import asyncio
import json
import time
from pricing import improve_on_best_quote

class TradingDashboard:
    def __init__(self):
        loop = asyncio.get_event_loop()
        # loop.run_until_complete(asyncio.gather(self.run_script()))
        loop.run_until_complete(asyncio.gather(self.configure_exchanges(), self.run_dashbaord()))

    def get_ws_uri(self, config, exchange_name):
        websocket_details = config['exchanges'][exchange_name]['websocket']
        uri = 'ws://' + str(websocket_details['ip']) + ':' + str(websocket_details['port']) + '/trader'
        print(uri)
        return uri

    async def configure_exchanges(self):
        with open('./configs/backend_config.json') as config_file:
            config = json.load(config_file)

            # self.GLOBITEX =  ExchangeConnection(enable_app=False, name='GLOBITEX', uri=self.get_ws_uri(config, 'globitex'))
            # self.KRAKEN =  ExchangeConnection(enable_app=False, name='KRAKEN', uri=self.get_ws_uri(config, 'kraken'))
            self.BITSTAMP =  ExchangeConnection(enable_app=False, name='BITSTAMP', uri=self.get_ws_uri(config, 'bitstamp'))
            self.LUNO =  ExchangeConnection(enable_app=True, name='LUNO', uri=self.get_ws_uri(config, 'luno'))
            self.EXCHANGES = [self.BITSTAMP, self.LUNO]

            await asyncio.gather(*[bot.connect_to_server() for bot in self.EXCHANGES])

    async def run_dashbaord(self):
            await asyncio.sleep(5)

            # G_BTCEUR =  Security('BTCEUR', self.GLOBITEX)
            B_BTCEUR =  Security('btceur', self.BITSTAMP)
            L_BTCEUR =  Security('XBTEUR', self.LUNO)

            # # G_SPREAD = L_BTCEUR - G_BTCEUR
            # H_SPREAD = L_BTCEUR - B_BTCEUR
            # # B_SPREAD = L_BTCEUR - B_BTCEUR

            # # self.LUNO.register_product(G_SPREAD, prefix='LUNO - GLOB')
            # self.LUNO.register_product(K_SPREAD, prefix='LUNO - KRAK')
            # # self.LUNO.register_product(B_SPREAD, prefix='LUNO - BITS')

            # Parley's Algo
            is_open = False
            LAhandle = 5 
            LBhandle = 5
            print("Started trading --------")
            qty_to_trade = 1
            away_from_best = -0.01

            while True:
                await asyncio.sleep(0.5)
                if not is_open:
                    # Note to self: -1 = Best Ask, 1 = Best Bid, 0 = Midprice
                    # print(G_SPREAD.evaluate(1))
                    l_ask = L_BTCEUR.evaluate(-1) 
                    b_bid = B_BTCEUR.evaluate(1) 
                    open_signal = l_ask - b_bid < -1 * LAhandle
                     
                    if open_signal:
                        print("Open Position:")
                        print("LMT - BUY [Luno BTC] @ %s [BEST ASK]" % l_ask)
                        print("LMT - SELL [Bitstamp BTC] @ %s [BEST BID]" % b_bid)
                        print("@Time: %s" % time.time())
                        LMT_ORDER_L = L_BTCEUR.to_order(qty=qty_to_trade, order_type='LMT', price_fn=improve_on_best_quote(away_from_best))
                        LMT_ORDER_B = -1 * (B_BTCEUR.to_order(qty=qty_to_trade, order_type='LMT', price_fn=improve_on_best_quote(away_from_best)))

                        assert(all(await asyncio.gather(*[LMT_ORDER_L, LMT_ORDER_B])))
                        # TODO: Figure out which trades to execute
                        is_open = True
                else:
                    l_bid = L_BTCEUR.evaluate(1) 
                    b_ask = B_BTCEUR.evaluate(-1) 
                    close_signal = l_bid - b_ask > LBhandle

                    if close_signal:
                        print("Close Position:")
                        print("LMT - SELL [Luno BTC] @ %s [BEST BID]" % l_bid)
                        print("LMT - BUY [Bitstamp BTC] @ %s [BEST ASK]" % b_ask)
                        print("@Time: %s" % time.time())
                        # TODO: Figure out which trades to execute

                        LMT_ORDER_L = -1 * L_BTCEUR.to_order(qty=qty_to_trade, order_type='LMT', price_fn=improve_on_best_quote(away_from_best))
                        LMT_ORDER_B =  B_BTCEUR.to_order(qty=qty_to_trade, order_type='LMT', price_fn=improve_on_best_quote(away_from_best))

                        assert(all(await asyncio.gather(*[LMT_ORDER_L, LMT_ORDER_B])))

                        is_open = False
                
TradingDashboard()