from frontend import Security, ExchangeConnection
from pricing import improve_on_best_quote
import asyncio
from multiprocessing import Process

class UnitTest():
    
    # -------- Helpers ----------
    def __init__(self):
        self.trader = ExchangeConnection(enable_app=True, name='TRADER')
        bot_1 = ExchangeConnection(enable_app=False, name='BOT1')
        bot_2 = ExchangeConnection(enable_app=False, name='BOT2')
        bot_3 = ExchangeConnection(enable_app=False, name='BOT3')
        self.mopup_bot = ExchangeConnection(enable_app=False, name='MOPUP')
        self.bots = [bot_1, bot_2, bot_3]

        loop = asyncio.get_event_loop()
        # loop.run_until_complete(asyncio.gather(self.run_script()))
        loop.run_until_complete(asyncio.gather(self.run_script()))

    @staticmethod
    async def assert_order_execution(*orders):
            # Market vs Market
            to_execute = [order.execute() for order in orders]
            assert(all(await asyncio.gather(*to_execute)))

    # -------- Tests ----------

    async def validate_pricing_functions(self):
        edge = 1
        direction = 1
        price_fn = improve_on_best_quote(edge)
        price_improved = price_fn(direction, self.RITC.evaluate)

        assert(price_improved == self.RITC.evaluate(direction) - 1)
        print("[TEST] Imporve on best quote: Success!")

    async def validate_graph_pricing(self):
        UNDERLYINGS = self.BEAR + self.BULL
        SPREAD = self.RITC - self.USD * UNDERLYINGS
        
        for i in [-1,0,1]:
            spread_price = SPREAD.evaluate(i)
            resolution = Security.resolution(spread_price)
            i_inv = -1 * i

            ritc_price = self.RITC.evaluate(i)
            self.BEAR.evaluate(i_inv)
            self.BULL.evaluate(i_inv)
            self.USD.evaluate(i)

            underlying_price =  self.BEAR.evaluate(i_inv) + self.BULL.evaluate(i_inv)
            true_spread_price = round(ritc_price - self.USD.evaluate(0) * underlying_price, resolution)
            
            assert(true_spread_price == spread_price)
        
        print("[TEST] Validate Graph Pricing : Success!")

    async def validate_mkt_order_execution(self):
        print("[TEST SUITE] Starting market order execution tests...")
        UNDERLYINGS = self.BEAR + self.BULL
        SPREAD = self.RITC - self.USD * UNDERLYINGS
        # SPREAD_USD_EXPSOURE = RITC * USD
        # HEDGED_SPREAD = SPREAD - SPREAD_USD_EXPSOURE

        ORDER = SPREAD.to_order(qty=100, order_type='MKT', group_name='MKT')
        SIGNED_ORDER = ORDER.inv_sign() * ORDER
        SIGNED_ORDER.group_name = 'SIGNED'
        await self.assert_order_execution(ORDER, SIGNED_ORDER)
        print("[TEST] Market - Market Order Transaction: Success!")

        # Simple Limit vs Market
        LMT_ORDER = self.RITC.to_order(qty=100, order_type='LMT', price_fn=improve_on_best_quote(1))
        MKT_ORDER = self.RITC.to_order(qty=100, order_type='MKT')
        SIGNED_MKT_ORDER = LMT_ORDER.inv_sign() * MKT_ORDER

        await self.assert_order_execution(LMT_ORDER, SIGNED_MKT_ORDER)
        print("[TEST] Limit - Market Order Transaction: Success!")

        # Complex vs Market
        # Note: A complex order is not added to the limit order book
        # Instead it is a Market Order with dispatch to server postponed until the limit price is within 
        # some threshold of the best quote.
        
        # It is first of all clear that for both Complex MKT and Complex LMT orders they should not be executed
        # until there is SUFFICIENT LIQUIDITY for all orders to be executed (TODO)

        # The issue with Complex LMT Orders is that we can't place limit orders for multiple underlying products
        # As we have more unkowns than equations (1 aggregate price target). Thus we will create a new order
        # type called CMPLX to stress the point that it is a market order executable subject to a condition 
        # rather than a limit order

        # TODO: Fix the contrived scenario to make it trigger the complex order. NOTE ADD Back in LMT_IMPROVE to execution
        # Contrived Orders to make the nex part of the test work
        # Imporve the best ask by 1
        # TODO: Fix this!
        LMT_IMPROVE = - 1 * self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(-1), group_name='LMT_IMPROVE')
        # Buy the spread at 1 below the market price -> Which we've setup to happen in the previous line!
        CMPLX_ORDER = SPREAD.to_order(qty=100, order_type='CMPLX', price_fn=improve_on_best_quote(1), group_name='CMPLX_ORDER') # Place a buy limit order at current market best bid

        # CMPLX_ORDER = SPREAD.to_order(qty=100, order_type='CMPLX', price_fn=improve_on_best_quote(0)) # Place a buy limit order at current market best bid
        MKT_ORDER = SPREAD.to_order(qty=100, order_type='MKT', group_name='MKT_ORDER')
        SIGNED_MKT_ORDER = SPREAD.inv_sign() * MKT_ORDER

        # Mops up the LMT_Imporve which did not improve enough to cross
        # the spread and thus was not executed as a marketable limit order
        LMT_IMPROVE_MOPUP = self.RITC.to_order(qty = 10, order_type = 'MKT', group_name='LMT_IMPROVE_MOPUP')
        
        await asyncio.gather(LMT_IMPROVE_MOPUP.execute_later(delay = 1), self.assert_order_execution(CMPLX_ORDER, LMT_IMPROVE, SIGNED_MKT_ORDER)) 
        
        print("[TEST] Complex Limit - Market Order Transaction: Success!")

        # Marketable Limit vs Limit
        LMT_IMPROVE = self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(-3), group_name='LMT_IMPROVE')

        LMT = -1 * self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(0), group_name='LMT')

        await self.assert_order_execution(LMT_IMPROVE, LMT)
        print("[TEST] Marketable Limit - Limit Order Transaction: Success!")

        # Marketable Limit vs Market

        LMT_IMPROVE = self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(-3), group_name='LMT_IMPROVE')

        MKT = -1 * self.RITC.to_order(qty = 10, order_type = 'MKT',group_name='MKT')

        await self.assert_order_execution(LMT_IMPROVE, MKT)
        print("[TEST] Marketable Limit - Limit Order Transaction: Success!")

        # Sequence Orders
        LMT = self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(0), group_name='LMT')
        MKT = -1 * self.RITC.to_order(qty = 20, order_type = 'MKT', group_name='MKT')
        MOPUP_LMT = self.RITC.to_order(qty = 10, order_type = 'LMT', price_fn=improve_on_best_quote(0), group_name='MOPUP_LMT')
        SEQ = LMT.then(MOPUP_LMT)

        await self.assert_order_execution(SEQ, MKT)
        print("[TEST] Sequence Order Transaction: Success!")
        print("[TEST SUITE] Finished market order execution tests...")
    
        # 
        # In order to do this we need to establish the frontend connection to the web app
        # TODO: Code up some bots (But again would be nice to have the trader private view first...)
        # Which will involve creating a private trader view
        
        # TODO: Test conditional orders
        # TODO: In order to test the this properly we need to be able to register and display
        # # synthetic product price charts to properly debug. 
        # NOTE: Think about converting mkt orders to limit orders
        # in very illiquid markets cause thr prices are probably 
        # really poor
        # TODO: Decide where to encorporate RISK MANAGEMENT into the frontend
        # maybe in the base_canc_execute blocks, but will need some explicit
        # lookahead management to see if the entire transaction sequence 
        # is feasible accross the entire algorithm :) Now that would be cool!
        # This is really important especially for tenders
        # TODO: Implement risk limits 

        # THRESHOLD = SPREAD.trade_costs()
        # CONDITIONAL_ORDER = SIGNED_ORDER % (SPREAD.abs() > THRESHOLD)
        # UNWIND_CONDITIONAL_ORDER = CONDITIONAL_ORDER.unwind() % (SPREAD * CONDITIONAL_ORDER.sign() > THRESHOLD)

        # PAIRED_ORDER = CONDITIONAL_ORDER.on_complete(UNWIND_CONDITIONAL_ORDER)

    async def validate_risk_monitor(self):
        print("[TEST SUITE] Starting Risk Monitor tests...")
        # ---- Simple Net Position offest check 1 - 1 ----
        # Note this is an edge case that checks we arent printing money
        # MKT vs MKT should be impossible for any trader to realise a net profit / loss
        # as they will be settled back at the midprice
        MKT_BUY = self.RITC.to_order(qty=30, order_type='MKT')
        # Cast the security to the bot's exchange connection and create an order
        MKT_SELLS = [-1 * self.RITC.assign_trader(bot).to_order(qty=10, order_type='MKT') for bot in self.bots]

        # Make sure all orders are executed
        await self.assert_order_execution(MKT_BUY, *MKT_SELLS)

        # Check that sum of bot net positions = -1 trader net position
        net_bot_positions = sum([bot._risk.net_position for bot in self.bots])
        bot_pnls = sum([bot._risk.pnl for bot in self.bots])

        net_trader_position = self.trader._risk.net_position
        trader_pnl = self.trader._risk.pnl

        assert(net_trader_position == -1 * net_bot_positions)
        assert(trader_pnl == 0) 
        assert(bot_pnls == 0)

        print("[TEST] Net Positions & PnL Basic Matching: Success")
        
        # ---- Simple Net Position offest check 1 - 1 in a MOVING market----
        # If the previous test no one could make money or lose money as 
        # they simply settled at the market midprice which hadn't changed
        # Now we will move the market by 1 point and the onls should be symmetric
        
        # The limit orders will shift the best bid best ask by 1 after the same transactions
        # as previous where completed
        LMT_BUY = self.RITC.assign_trader(self.mopup_bot).to_order(qty=30, order_type='LMT', price_fn=improve_on_best_quote(-1))
        LMT_SELL = -1 * self.RITC.assign_trader(self.mopup_bot).to_order(qty=30, order_type='LMT', price_fn=improve_on_best_quote(1))

        # Make sure all orders are executed
        async def check_pnls():
            await asyncio.sleep(1) # Ensures the market moving orders
            # have been executed first
            # NOTE I did have an issue when i shortened this sleep
            # so this is a hack for sure
            # but its not something we normally would do in the course of trading
            # so it should be fine.
            
            # Check that sum of bot net positions = -1 trader net position
            net_bot_positions = sum([bot._risk.net_position for bot in self.bots])
            bot_pnls = sum([bot._risk.pnl for bot in self.bots])

            net_trader_position = self.trader._risk.net_position
            trader_pnl = self.trader._risk.pnl

            assert(net_trader_position == -1 * net_bot_positions)
            assert(trader_pnl == -1 * bot_pnls) 
            assert(trader_pnl != 0) 
            assert(self.trader._risk.realised == 0)

            print("[TEST] Net Positions & PnL Basic Moving Market: Success")

            # ---- Realised PNL Check ----
            # Now that we have non zero pnls we want to realise 1/2 of it
            # and check that realised pnl's are correct (50 50 split)

            # Since the market orders came earlier than the limit
            # which raised the bid the bot traders will take the hit to
            # there realised pnl

            # First we need to mopup those limits so they don't get in the way
            MKT_BUY = self.RITC.assign_trader(self.mopup_bot).to_order(qty=30, order_type='MKT')
            MKT_SELL = -1 * self.RITC.assign_trader(self.mopup_bot).to_order(qty=30, order_type='MKT')

            await self.assert_order_execution(MKT_BUY, MKT_SELL)

            # Now Lets sell half the traders stock
            MKT_SELL = -1 * self.RITC.to_order(qty=15, order_type='MKT')
            MKT_BUYS = [self.RITC.assign_trader(bot).to_order(qty=5, order_type='MKT') for bot in self.bots]

            await self.assert_order_execution(MKT_SELL, *MKT_BUYS)

            # Checks the realised risk and unrealised has been split correctly
            assert(self.trader._risk.realised == self.trader._risk.unrealised)
            assert(self.trader._risk.realised != 0)
            assert(self.trader._risk.pnl == trader_pnl)

            last_bots_pnl = bot_pnls
            bots_realised = sum([bot._risk.realised for bot in self.bots])
            bots_unrealised = sum([bot._risk.unrealised for bot in self.bots])
            bot_pnls = sum([bot._risk.pnl for bot in self.bots])
            
            assert(bots_realised == bots_unrealised)
            assert(bot_pnls != 0)
            assert(bot_pnls == last_bots_pnl)

            print("[TEST] Realised and unrealised pnl working as expected: Success")

        await asyncio.gather(self.assert_order_execution(LMT_BUY, LMT_SELL), check_pnls())
        print("[TEST SUITE] Finished Risk Monitor Tests...")

    async def visual_inspection_test(self):
        UNDERLYINGS = self.BEAR + self.BULL
        SPREAD = self.RITC - self.USD * UNDERLYINGS

        # # Test Visual 1
        # LMT_ORDER = self.RITC.to_order(qty=100, order_type='LMT', price_fn=improve_on_best_quote(1))
        # MKT_ORDER = -1 * self.RITC.to_order(qty=100, order_type='MKT')

        # assert(all(await asyncio.gather(MKT_ORDER.execute_later(5), LMT_ORDER.execute())))

        # # Test Visual 2
        # LMT_ORDER = SPREAD.to_order(qty=100, order_type='MKT')
        # MKT_ORDER = -1 * SPREAD.to_order(qty=100, order_type='MKT')

        # assert(all(await asyncio.gather(MKT_ORDER.execute_later(5), LMT_ORDER.execute())))

        # # Test 3 Present Single Limit Order
        # LMT_ORDER = self.RITC.to_order(qty=100, order_type='LMT', price_fn=improve_on_best_quote(1))
        # await LMT_ORDER.execute()

        # Test 4 Table Scrolling
        # LMT_ORDER = self.RITC.to_order(qty=100, order_type='LMT', price_fn=improve_on_best_quote(1))
        # LMT_ORDER_2 = -1*self.RITC.to_order(qty=100, order_type='LMT', price_fn=improve_on_best_quote(1))
        # # Then check order fill qtys working visually
        # MKT_ORDER = self.RITC.to_order(qty=50, order_type='MKT')
        
        # await self.assert_order_execution(*([LMT_ORDER]*20 + [LMT_ORDER_2]*20), MKT_ORDER)

        # Test 5 Market Dashboard
        MKT_ORDER = SPREAD.to_order(qty=50, order_type='MKT')
        LMT_ORDER = self.RITC.to_order(qty=50, order_type='LMT', price_fn=improve_on_best_quote(1))
        LMT_ORDER_2 = self.RITC.to_order(qty=50, order_type='LMT', price_fn=improve_on_best_quote(2))
        LMT_ORDER_3 = -1 * self.RITC.to_order(qty=50, order_type='LMT', price_fn=improve_on_best_quote(1))

        # # Then check order fill qtys working visually
        MKT_ORDER_2 = -1 *self.RITC.to_order(qty=50, order_type='MKT')
        MKT_ORDER_3 = -1 * self.RITC.to_order(qty=23, order_type='MKT')

        await self.assert_order_execution(*([LMT_ORDER]*20 + [LMT_ORDER_2]*20 + [MKT_ORDER] * 20 + [LMT_ORDER_3] * 25), MKT_ORDER_2, MKT_ORDER_3)
        
        print('[TEST] Visual Tests Complete!') # Obviously not going to get called :)
        # As we didnt square the position above
    
    async def connect_traders(self):
        await asyncio.gather(self.trader.connect_to_server(), *[bot.connect_to_server() for bot in self.bots], self.mopup_bot.connect_to_server())

    def configure_securities(self):
        self.RITC = Security('RITC', self.trader)
        self.BEAR = Security('BEAR', self.trader)
        self.BULL = Security('BULL', self.trader)
        self.USD = Security('USD', self.trader)

    async def run_tests(self):
        await asyncio.sleep(0.5) # Let connection configure
        self.configure_securities()

        print('[Tests] Starting...')
        await asyncio.gather(self.validate_graph_pricing(),self.validate_pricing_functions(), self.validate_mkt_order_execution())
        # await asyncio.gather(self.visual_inspection_test())
        
        # NOTE the validate_mkt_order_execution will mess up
        # validate risk monitor as it makes the bid ask spread 
        # invert which is not going to produce expected results :)
        # TODO: Implement prevent self trades [This will be incompatible with validate_mkt_order_execution] but in real trading environment we should stop this from happening
        # We will need to decide how best to catch these double sided entries...
        await self.validate_risk_monitor()

    async def run_script(self):
        
        await asyncio.gather(self.connect_traders(), self.run_tests())


"""
Run Unit Tests
"""
UnitTest()