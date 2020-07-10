import websockets
import json
import asyncio
import time
import sqlite3
from sqlite3 import Error

class Database:
    def __init__(self):
        self._db_path = './datasets/markets.db'
        self._setup_path = './datasets/markets_setup.txt'
        self.verbose = True

    def log(self, s):
        if self.verbose:
            print(s)

    def create_connection(self, db_file):
        """ create a database connection to the SQLite database specified by db_file
        :param db_file: database file
        :return: Connection object or None
        """
        self.conn = None
        try:
            self.conn = sqlite3.connect(db_file)
        except Error as e:
            print('[Database] Error:')
            print(e)
        
        return self.conn

    def run_setup_script(self, script_path):
        """ create a table from the create_table_sql statement
        :param conn: Connection object
        :param create_table_sql: a CREATE TABLE statement
        :return:
        """
        try:
            f = open(script_path, 'r')
            setup_script = f.read()
            # print(setup_script)
            c = self.conn.cursor()
            c.executescript(setup_script)
        except (Error, IOError) as e:
            print('[Datanase] Error:')
            print(e)    

    def __enter__(self):
        if self.create_connection(self._db_path):
            self.run_setup_script(self._setup_path)
            self.log('[Database] Connected to db @ %s' % self._db_path)
            return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn:
            # Always close db when finished
            self.log('[Database] Disconnected from db @ %s' % self._db_path)
            self.conn.commit()
            self.conn.close()

    def update_prices(self, books, exchange_name):
        try:
            c = self.conn.cursor()
            
            for ticker, book in books.items():
                timestamp = time.time()
                best_bid = book['best_bid']
                best_ask = book['best_ask']
                bid_depth = book['bid_depth']
                ask_depth = book['ask_depth']
                bid_volume = book['bid_volume']
                ask_volume = book['ask_volume']
                n_bids = book['n_bids']
                n_asks = book['n_asks']

                sql = """INSERT OR REPLACE INTO prices (timestamp,exchange,ticker,best_bid,best_ask, bid_depth, ask_depth, bid_volume, ask_volume, n_bids, n_asks, l2_ask, l3_ask, l4_ask, l5_ask, l2_bid, l3_bid, l4_bid, l5_bid, l1_ask_vol, l2_ask_vol, l3_ask_vol, l4_ask_vol, l5_ask_vol, l1_bid_vol, l2_bid_vol, l3_bid_vol, l4_bid_vol, l5_bid_vol) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
                
                # TODO: Refactor this!
                bid_prices = list(reversed(sorted(book['bid_book'].keys())))
                ask_prices = list(sorted(book['ask_book'].keys()))

                ask_levels = [0 for i in range(1,5)]
                ask_vol_levels = [0 for i in range(0,5)]
                bid_levels = [0 for i in range(1,5)]
                bid_vol_levels = [0 for i in range(0,5)]

                if len(bid_prices) > 0:
                    bid_vol_levels[0] = bid_prices[0]

                if len(ask_prices) > 0:
                    bid_vol_levels[0] = ask_prices[0]

                for i in range(1,min(5, len(ask_prices))):
                    ask = ask_prices[i]
                    ask_vol = sum([order['qty'] - order['qty_filled'] for order in book['ask_book'][ask]])
                    ask_levels[i-1] = ask
                    ask_vol_levels[i-1] = ask_vol

                for i in range(1,min(5, len(bid_prices))):
                    bid = bid_prices[i]
                    bid_vol = sum([order['qty'] - order['qty_filled'] for order in book['bid_book'][bid]]) 
                    bid_levels[i-1] = bid
                    bid_vol_levels[i-1] = bid_vol

                # print("Adding Record: ", (timestamp, exchange_name, ticker, best_bid, best_ask))
                c.execute(sql, (timestamp, exchange_name, ticker, best_bid, best_ask, bid_depth, ask_depth, bid_volume, ask_volume, n_bids, n_asks,*ask_levels, *bid_levels, *ask_vol_levels, *bid_vol_levels))

            self.conn.commit()
        except Error as e:
            print('[Database] Error:')
            print(e)