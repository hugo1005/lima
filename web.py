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
            print(setup_script)
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

                sql = """INSERT OR REPLACE INTO prices (timestamp,exchange,ticker,best_bid,best_ask, bid_depth, ask_depth, bid_volume, ask_volume, n_bids, n_asks) VALUES (?,?,?,?,?,?,?,?,?,?,?)"""
                
                c.execute(sql, (timestamp, exchange_name, ticker, best_bid, best_ask, bid_depth, ask_depth, bid_volume, ask_volume, n_bids, n_asks))
                
            self.conn.commit()
        except Error as e:
            print('[Database] Error:')
            print(e)

class WebServer:
    def __init__(self, backend_config_dir = './configs/backend_config.json', frontend_config_dir = './configs/frontend_config.json', ):
        with open(frontend_config_dir) as config_file:
            self.frontend_config = json.load(config_file)

        with open(backend_config_dir) as config_file:
            self.backend_config = json.load(config_file)

        self._port_frontend = self.frontend_config['app-websocket']['port']
        self._port_backend = self.backend_config['app-websocket']['port']
        self._ip_frontend = self.frontend_config['app-websocket']['ip']
        self._ip_backend = self.backend_config['app-websocket']['ip']
       
        # self.frontend_app = None
        # self.frontend = None
        
        self.frontend_to_app_cache = []
        self.backend_to_app_cache = []
        self.backend_to_app_config_cache = []
        self.backend_has_updates = asyncio.Event()
        self.frontend_has_updates = asyncio.Event()

        # Debounce LOB messages to every 300 ms
        self._debounce = 0.3
        # Simple hack to ensure the first LOBs always sent
        self.last_posts = {s_type: time.time() - (self._debounce + 0.2) for s_type in ['LOBS','pnl','risk','MBS']}

        self.setup_websocket_server()

    def setup_websocket_server(self):
        print("Initialising websocket...")

        # Initialises the server and ensures it winds down gracefully
        loop = asyncio.get_event_loop()
       
        frontend_handler = websockets.serve(self.bridge_frontend, self._ip_frontend, self._port_frontend, max_size = None)
        backend_handler = websockets.serve(self.bridge_backend, self._ip_backend, self._port_backend, max_size = None)

        handlers = asyncio.gather(frontend_handler, backend_handler)

        servers = loop.run_until_complete(handlers)

        loop.run_forever()

        # Close the server
        for server in servers:
            server.close()

        loop.run_until_complete(server.wait_closed())

    async def bridge_backend(self, ws, path):
        is_backend, is_app = path == '/backend', path == '/app'

        try:
            if is_backend:
                print("Backend connection established")
                # Store the data for sending to the server.
                exchange_name = 'unkown'
                # Create SQL Connection
                with Database() as db:
                    while True:
                        data = await ws.recv()
                        msg = json.loads(data)
                        msg_type = msg['type']

                        # This must always be the first message sent from the server
                        if msg_type == 'config':
                            self.backend_to_app_cache.append(data)
                            self.backend_to_app_config_cache.append(data)
                            self.n_config_messages = msg['n_config_messages']
                            exchange_name = msg['data']['exchange_name']

                        # Handles caching of key setup information
                        elif len(self.backend_to_app_config_cache) < self.n_config_messages:
                            self.backend_to_app_config_cache.append(data)

                        if msg_type in self.last_posts:
                            if self.last_posts[msg_type] < time.time() - self._debounce:
                                self.backend_to_app_cache.append(data)
                                self.backend_has_updates.set()
                                self.last_posts[msg_type] = time.time() 
                        else:
                            self.backend_to_app_cache.append(data)
                            self.backend_has_updates.set()

                        if msg_type == 'LOBS':
                            db.update_prices(msg['data'], exchange_name)
            
            elif is_app: 
                print("App [Backend State Management] connection established")
            
                # Send any critical setup information once off
                for data in self.backend_to_app_config_cache:
                    await ws.send(data)

                # Pass messages from backend to frontend
                while True:
                    await self.backend_has_updates.wait()
                    self.backend_has_updates.clear()

                    while len(self.backend_to_app_cache) > 0:
                        # Send in time order
                        dispatch = self.backend_to_app_cache.pop(0)
                        await ws.send(dispatch)

        except websockets.ConnectionClosed:
            print("Connection with [%s] closed: [%s]" % (path, time.time())) 
        finally:
            if is_backend:
                self.backend_to_app_cache = []

    async def bridge_frontend(self, ws, path):
        is_frontend, is_app = path == '/frontend', path == '/app'

        try:
            if is_app: 
                print("App [Frontend State Management] connection established")

                # Pass messages from backend to frontend
                while True:
                    await self.frontend_has_updates.wait()
                    self.frontend_has_updates.clear()

                    while len(self.frontend_to_app_cache) > 0:
                        # Send in time order
                        dispatch = self.frontend_to_app_cache.pop(0)
                        await ws.send(dispatch)

            if is_frontend:
                print("Frontend connection established")
                # Store the data for sending to the server.
                while True:
                    data = await ws.recv()
                    self.frontend_to_app_cache.append(data)
                    self.frontend_has_updates.set()
                    
        except websockets.ConnectionClosed:
            print("Connection with [%s] closed: [%s]" % (path, time.time())) 
        finally:
            if is_frontend:
                self.frontend_to_app_cache = []

"""Start the webserver"""
WebServer()


