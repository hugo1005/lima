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

# This is only a temporary version to get a working market
class MarketDynamics:
    def __init__(self, traders, ticker, book, case_config, time_fn):
        self._case_config = case_config
        self._security_config = case_config['securities'][ticker]
        self._traders = traders
        self._ticker = ticker
        self._time_fn = time_fn
        self._step = 0
        self._tender_id = 0
        self._book = book # Book of the relevant security

        self._market_dynamics = self._security_config['market_dynamics']
        self._price_path = self._market_dynamics['price_path']
        self._tender_config = self._market_dynamics['institutional_orders']
        self._tenders_enabled = self._tender_config['enabled']
        
        # ------------ market parameters --------------
        self._midprice = self._security_config['starting_price']
        # What is the minium decimal places to display
        self._resolution = self._security_config['resolution']
        # How man times per second to update the market price 
        self._updates_per_second = self._price_path['updates_per_second']
        # The notional market time corresponding to a single price update
        self._notional_timestep = self._case_config['simulation_notional_timestep'] 
        # The sleep delay between steps
        self._step_price_delay = 1 / self._updates_per_second

        # Assuming 250 trading days per year
        trading_year_in_seconds = 60 * 60 * 24 * 250
        # Value of one step every _step_price_delay as a fraction of the trading year
        self._timestep = self._notional_timestep / trading_year_in_seconds
        # Annualised volatilty and expected returns
        self._expected_return = self._price_path['expected_return']
        self._volatility = self._price_path['volatility']

        # ------------- Tender Paramaters --------------------
        if self._tenders_enabled:
            # self._automated_trader_config = self._market_dynamics['automated_traders']
            # self._automated_traders = []

            # tender specification
            tenders_per_price_step = self._tender_config['avg_num_tenders_per_second'] / self._updates_per_second
            self._tender_rate = tenders_per_price_step
            self._expires_after = self._tender_config['expires_after']
            
            # Solve for gamma(a,b) given variance and b = 2
            mean = self._tender_config["tender_price_mean"]
            variance = self._tender_config["tender_price_deviation"]**2

            self._gamma_a, self._gamma_b = ((mean**2) / variance), (mean / variance)
            
            # Shift the distribution so quotes at undesirable prices are possible
            rv = gamma(self._gamma_a, scale = 1/self._gamma_b)
            self._gamma_shift = rv.ppf(self._tender_config['prob_of_bad_tender_price'])

            self._expected_tender_qty = self._tender_config["expected_tender_qty"]

    async def create_dynamics(self):
        await asyncio.sleep(0.5) # Allows the websocket server to become operational

        print("Creating Market Dynamics...")

        # if self._tenders_enabled:
        #     for traderType, count in self._automated_trader_config.items():
        #         if traderType == 'giveaway_trader':
        #             self._automated_traders += [GiveawayTrader() for i in range(0, count)]

        #     trader_activations = asyncio.gather(*[t.connect() for t in self._automated_traders])
        #     print("Activating automated traders...")
        #     await asyncio.gather(trader_activations, self.step_market_price_path())
        # else:
        #     await self.step_market_price_path()

        await self.step_market_price_path()

    async def step_market_price_path(self):
        while True:
            # TODO: This is a rather simple model of price we can introduce more variables
            # such as market shocks but this will do for now.

            # GBM Price Path
            drift = self._expected_return * self._timestep
            shock = self._volatility * normalvariate(0, 1) * np.sqrt(self._timestep)
            price_change = self._midprice * (drift + shock) # Price change is the shocked timestep return * current price
            self._midprice = self._midprice + price_change
        
            # Only do this once per second
            if self._tenders_enabled and self._step % self._updates_per_second == 0:
                await self.generate_tenders()
            
            await asyncio.sleep(self._step_price_delay)
            self._step += 1

    async def generate_tenders(self):
        tenders = []
        tids = [*self._traders]

        if len(tids) > 0:
            # Tenders simultaneously requested at a poisson rate
            num_tenders = poisson(lam=self._tender_rate)
            
            tenders += await asyncio.gather(*[self.create_tender(self._ticker, choice(['BUY', 'SELL']), self._traders[choice(tids)]) for tender in range(0,num_tenders)])

    @staticmethod
    def round_to_2_sf(x):
        return round(x, 1-int(floor(log10(abs(x)))))

    async def create_tender(self, ticker, action, trader):
        # Desired shape and expected value
        tender_qty = self.round_to_2_sf(self._expected_tender_qty * 3/2 * betavariate(3, 1.5))
        
        # Desired risk premium paid by the client
        improvement_on_best_quote = gammavariate(self._gamma_a, self._gamma_b)
        spread = self._book._asks.best_price - self._book._bids.best_price
        
        # If the action is BUY (we are buying from the client) so we
        # need to be able to sell at at a price >= midprice >= best bid

        if action == 'BUY':
            tender_price = (self._midprice - spread/2) - improvement_on_best_quote + self._gamma_shift
        else:
            tender_price = (self._midprice + spread/2) + improvement_on_best_quote - self._gamma_shift

        tender_price = round(tender_price, self._resolution)

        tender_order = TenderOrder(ticker, self.get_next_tender_id(), tender_qty, action, tender_price, self._time_fn() + self._expires_after)

        await trader.send(json.dumps({'type': 'tender', 'data': named_tuple_to_dict(tender_order)}))
        return tender_order
        # SEND TO TRADERS WHEN COMPUTED

    def get_next_tender_id(self):
        tender_id = 'tender_' + str(self._tender_id)
        self._tender_id += 1

        return tender_id
