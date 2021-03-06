from frontend import Security, ExchangeConnection
import asyncio
import json
import time
from pricing import improve_on_best_quote
from traders import StatArbTrader
import numpy as np

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
            # self.BITSTAMP =  ExchangeConnection(enable_app=False, name='BITSTAMP', uri=self.get_ws_uri(config, 'bitstamp'))
            self.LUNO =  ExchangeConnection(enable_app=False, name='LUNO', uri=self.get_ws_uri(config, 'luno'))
            # self.EXCHANGES = [self.BITSTAMP, self.LUNO]
            self.EXCHANGES = [self.LUNO]

            await asyncio.gather(*[bot.connect_to_server() for bot in self.EXCHANGES])

    async def run_dashbaord(self):
            await asyncio.sleep(5)

            # G_BTCEUR =  Security('BTCEUR', self.GLOBITEX)
            # B_BTCEUR =  Security('btceur', self.BITSTAMP)
            L_BTCEUR =  Security('XBTEUR', self.LUNO)

            init_qty = 0.007
            is_buying = False
            fee = 0.005

            while True:
                wait_time = np.random.normal(10, 5, 1)
                await asyncio.sleep(wait_time)
                print("Is Buying: %s " % is_buying)
                
                if is_buying:
                    ORDER = L_BTCEUR.to_order(
                        qty=init_qty,
                        order_type='MKT'
                    ) 
                else:
                    ORDER = -1 * L_BTCEUR.to_order(
                        qty=init_qty,
                        order_type='MKT'
                    )

                await ORDER.execute()
                is_buying = not is_buying

                print("Order completed, moving to the next one")
                await asyncio.sleep(5)



            # self.execution_price = {1:None,-1:None}

            # def cross_spread(direction, evaluate):
            #     # This function ensures our first order is placed into the spread
            #     # So that we are more likely to get filled

            #     # Best Ask - Best Bid
            #     spread = abs(evaluate(-1) - evaluate(1))
            #     spread_plus = spread * 0.2
            #     # Buy
            #     marketable_buy_price = evaluate(1) + spread_plus
            #     marketable_sell_price = evaluate(-1) - spread_plus
            #     is_buying = direction == 1

            #     price = round(marketable_buy_price if is_buying else marketable_sell_price,2)
            #     print("Placing limit %s order @ %s" % ('BUY' if is_buying else 'SELL', price))

            #     self.execution_price[direction] = price

            #     return price

            # # # make_profit and cover_loss specify our assympetric risk reward for closing out position
            # # # with initial open price specified by cross spread
            # def make_profit(direction, evaluate):
            #     spread = abs(evaluate(-1) - evaluate(1))
            #     is_buying = direction == 1

            #     return round(self.execution_price[direction * -1] - spread if is_buying else self.execution_price[direction * -1] + spread,2)

            # # def cover_loss(direction, evaluate):
            # #     spread = evaluate(-1) - evaluate(1)
            # #     is_buying = direction == 1

            # #     return execution_price + spread * 0.5 if is_buying else execution_price - spread * 0.5

            # async def on_timeout(filled, unfilled):
            #     # Our initial order is regularly pulled and replaced at a new price

            #     # Cancel the unfilled LMT orders
            #     cancellation_events = {order_id: asyncio.Event() for order_id in unfilled}
            #     unfilled_orders = list(unfilled.values())

            #     print("Pulling limit orders from exchange")
            #     self.LUNO.cancel_orders(unfilled_orders, cancellation_events)
            #     await asyncio.gather(*[event.wait() for _, event in cancellation_events.items()])
            #     print("Limit orders pulled from exchange")

            # async def manage_downside_risk(filled, unfilled):
            #     # this is a hack
            #     # we will use an very fast timeout duration
            #     # so that we can now specify and additional order for covering our downside
            #     # we will then cancel the non executed order

            #     # Cancel the unfilled LMT orders
            #     cancellation_events = {order_id: asyncio.Event() for order_id in unfilled}
            #     unfilled_orders = list(unfilled.values())
                
            #     self.LUNO.cancel_orders(unfilled_orders, cancellation_events)
            #     await asyncio.gather(*[event.wait() for _, event in cancellation_events.items()])
                
            #     order = unfilled_orders[0]
            #     sec = L_BTCEUR
            #     spread = abs(sec.evaluate(-1) - sec.evaluate(1))
            #     is_buying = order.action == 'BUY'
            #     direction = 1 if is_buying else -1

            #     profit_price = self.execution_price[direction * -1] - spread * 4 if is_buying else self.execution_price[direction * -1] + spread * 4
            #     loss_price = self.execution_price[direction * -1] + spread * 2 if is_buying else self.execution_price[direction * -1] - spread * 2
                
            #     print("Is buying: @ %s " % (is_buying))
            #     print("In Position: will take profit @ %s will take loss @ %s " % (profit_price, loss_price))

            #     # Setup our 2 orders
            #     CLOSE_POS = L_BTCEUR.to_order(
            #         qty=0.0025,
            #         order_type='MKT',
            #     ) 

            #     while True:
            #         await asyncio.sleep(1)
            #         current_price = sec.evaluate(-1 * direction) # Going to cross spread to exit hence inv_sign
                    
            #         current_time = time.time()
            #         duration_remaining = self.end_time - current_time

            #         if current_price >= profit_price or current_price <= loss_price:
            #             print("Closing out position...")
            #             await (direction * CLOSE_POS).execute()
            #             print("Position closed")
            #             break

            # self.start_time = time.time()  
            # self.time_limit = 10 * 60 #
            # self.end_time = self.start_time + self.time_limit

            # while True:
                
            #     current_time = time.time()
            #     duration_remaining = self.end_time - current_time
            #     timeout_seconds = min(duration_remaining, 20)

            #     OPEN_POS = L_BTCEUR.to_order(
            #         qty=0.0025,
            #         order_type='LMT',
            #         price_fn= cross_spread,
            #         timeout = timeout_seconds,
            #         timeout_fn = on_timeout
            #     ) # BUY

            #     CLOSE_POS = L_BTCEUR.to_order(
            #         qty=0.0025,
            #         order_type='LMT',
            #         price_fn=make_profit,
            #         timeout = 1,
            #         timeout_fn = manage_downside_risk
            #     ) # BUY

            #     IMPROVE_ON_ASK = OPEN_POS.unwind()
            #     IMPROVE_ON_BID = OPEN_POS # Buy

            #     CLOSE_IMPROVE_ON_ASK = CLOSE_POS
            #     CLOSE_IMPROVE_ON_BID = CLOSE_POS.unwind() # Sell

            #     SELL_STRAT = IMPROVE_ON_ASK.then(CLOSE_IMPROVE_ON_ASK)
            #     BUY_STRAT = IMPROVE_ON_BID.then(CLOSE_IMPROVE_ON_BID)

            #     # market_making = [SELL_STRAT.execute(), BUY_STRAT.execute()]
            #     market_making = [BUY_STRAT.execute(), SELL_STRAT.execute()]
            #     print("=== Executing Market Making Strat ====")
            #     await asyncio.gather(*market_making) # SELL
            #     print("=== Restarting Strat ====")
            #     await asyncio.sleep(5)

            # print('==== Cycle Complete! =====')
            # while True:
            #     await asyncio.sleep(1) # holding pattern

            # print('-------- BITSTAMP ---------')

            # OPEN_BITSTAMP_POSITION = (B_BTCEUR.to_order(
            #     qty=0.003,
            #     order_type='LMT',
            #     price_fn=cross_spread
            # )) # BUY

            # await asyncio.gather(*[OPEN_BITSTAMP_POSITION.unwind().execute()]) # SELL
            # print("1st Trade complete")
            # await asyncio.sleep(1)
            # await asyncio.gather(*[OPEN_BITSTAMP_POSITION.execute()]) # BUY
            # print("2nd Trade complete")

            # print('--------- LUNO ------------')

            # OPEN_LUNO_POSITION = (L_BTCEUR.to_order(
            #     qty=0.003,
            #     order_type='MKT'
            # )) # BUY

            # await asyncio.gather(*[OPEN_LUNO_POSITION.unwind().execute()]) # SELL
            # print("1st Trade complete")
            # await asyncio.sleep(1)
            # await asyncio.gather(*[OPEN_LUNO_POSITION.execute()]) # BUY
            # print("2nd Trade complete")

            # # G_SPREAD = L_BTCEUR - G_BTCEUR
            # H_SPREAD = L_BTCEUR - B_BTCEUR
            # # B_SPREAD = L_BTCEUR - B_BTCEUR

            # # self.LUNO.register_product(G_SPREAD, prefix='LUNO - GLOB')
            # self.LUNO.register_product(K_SPREAD, prefix='LUNO - KRAK')
            # # self.LUNO.register_product(B_SPREAD, prefix='LUNO - BITS')

            # # Parley's Algo
            # is_open = False
            # LAhandle = 5 
            # LBhandle = 5
            # print("Started trading --------")
            # while True:
            #     if not is_open:
            #         # Note to self: -1 = Best Ask, 1 = Best Bid, 0 = Midprice
            #         # print(G_SPREAD.evaluate(1))
            #         l_ask = L_BTCEUR.evaluate(-1) 
            #         b_bid = B_BTCEUR.evaluate(1) 
            #         open_signal = l_ask - b_bid < -1 * LAhandle
                    
            #         if open_signal:
            #             print("Open Position:")
            #             print("LMT - BUY [Luno BTC] @ %s [BEST ASK]" % l_ask)
            #             print("LMT - SELL [Bitstamp BTC] @ %s [BEST BID]" % b_bid)
            #             print("@Time: %s" % time.time())
            #             # TODO: Figure out which trades to execute
            #             is_open = True

            #     else:
            #         l_bid = L_BTCEUR.evaluate(1) 
            #         b_ask = B_BTCEUR.evaluate(-1) 
            #         close_signal = l_bid - b_ask > LBhandle

            #         if close_signal:
            #             print("Close Position:")
            #             print("LMT - SELL [Luno BTC] @ %s [BEST BID]" % l_bid)
            #             print("LMT - BUY [Bitstamp BTC] @ %s [BEST ASK]" % b_ask)
            #             print("@Time: %s" % time.time())
            #             # TODO: Figure out which trades to execute
            #             is_open = False
            
            # print("Started Ended --------")


TradingDashboard()



