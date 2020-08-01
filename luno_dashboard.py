from frontend import Security, ExchangeConnection
import asyncio
import json

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
            self.KRAKEN =  ExchangeConnection(enable_app=False, name='KRAKEN', uri=self.get_ws_uri(config, 'kraken'))
            # self.BITSTAMP =  ExchangeConnection(enable_app=False, name='BITSTAMP', uri=self.get_ws_uri(config, 'bitstamp'))
            self.LUNO =  ExchangeConnection(enable_app=True, name='LUNO', uri=self.get_ws_uri(config, 'luno'))
            self.EXCHANGES = [self.KRAKEN, self.LUNO]

            await asyncio.gather(*[bot.connect_to_server() for bot in self.EXCHANGES])

    async def run_dashbaord(self):
            await asyncio.sleep(5)

            # G_BTCEUR =  Security('BTCEUR', self.GLOBITEX)
            K_BTCEUR =  Security('XBTEUR', self.KRAKEN)
            # B_BTCEUR =  Security('btceur', self.BITSTAMP)
            L_BTCEUR =  Security('XBTEUR', self.LUNO)

            # G_SPREAD = L_BTCEUR - G_BTCEUR
            K_SPREAD = L_BTCEUR - K_BTCEUR
            # B_SPREAD = L_BTCEUR - B_BTCEUR

            # self.LUNO.register_product(G_SPREAD, prefix='LUNO - GLOB')
            self.LUNO.register_product(K_SPREAD, prefix='LUNO - KRAK')
            # self.LUNO.register_product(B_SPREAD, prefix='LUNO - BITS')

            while True:
                await asyncio.sleep(1)
                # print(G_SPREAD.evaluate(1))
                print("LUNO b/a", L_BTCEUR.evaluate(1), L_BTCEUR.evaluate(-1))
                print("KRAK b/a", K_BTCEUR.evaluate(1), K_BTCEUR.evaluate(-1))

                buy_spread = (K_BTCEUR - L_BTCEUR).evaluate(1)
                sell_spread = (K_BTCEUR - L_BTCEUR).evaluate(-1)
                print(buy_spread)
                print(sell_spread)
                print("Edge:", -1 * buy_spread + sell_spread)
                # print(B_SPREAD.evaluate(1))


TradingDashboard()