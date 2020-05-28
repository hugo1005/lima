import websockets
import json
import asyncio
import time

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
       
        self.frontend_app = None
        self.frontend = None
        
        self.frontend_to_app_cache = []
        self.backend_to_app_cache = []
        self.backend_has_updates = asyncio.Event()

        self.setup_websocket_server()

    def setup_websocket_server(self):
        print("Initialising websocket...")

        # Initialises the server and ensures it winds down gracefully
        loop = asyncio.get_event_loop()
       
        frontend_handler = websockets.serve(self.bridge_frontend, self._ip_frontend, self._port_frontend)
        backend_handler = websockets.serve(self.bridge_backend, self._ip_backend, self._port_backend)

        handlers = asyncio.gather(frontend_handler, backend_handler)

        servers = loop.run_until_complete(handlers)

        loop.run_forever()

        # Close the server
        for server in servers:
            server.close()

        loop.run_until_complete(server.wait_closed())
    
    # TODO: Decouple the bridge_frontend like backend
    async def bridge_frontend(self, ws, path):
        is_frontend, is_app = path == '/frontend', path == '/app'

        # Register connection
        if is_frontend:
            print("Frontend connection established")
            self.frontend = ws
        elif is_app:
            print("App [Frontend State Management] connection established")
            self.frontend_app = ws
        else:
            print("Websocket path unkown: %s" % path)
        
        try:
            if is_app: # Replay all messages to catch up
                print("Replaying frontend data..")
                for data in self.frontend_to_app_cache:
                    await self.frontend_app.send(data)

            async for data in ws:
                both_connected = type(self.frontend_app) != type(None) and type(self.frontend) != type(None)
                
                if is_frontend:
                    self.frontend_to_app_cache.append(data)
                    
                    if both_connected:
                        await self.frontend_app.send(data)
                
                if is_app and both_connected:
                    await self.frontend.send(data)

        except websockets.ConnectionClosed:
            print("Connection with [%s] closed" % path) 
        finally:
            if is_frontend: 
                self.frontend = None
                self.frontend_to_app_cache = [] # Clear the message cache
            if is_app: self.frontend_app = None

    async def bridge_backend(self, ws, path):
        is_backend, is_app = path == '/backend', path == '/app'

        try:
            if is_app: 
                print("App [Backend State Management] connection established")

                # Pass messages from backend to frontend
                while True:
                    await self.backend_has_updates.wait()
                    self.backend_has_updates.clear()

                    while len(self.backend_to_app_cache) > 0:
                        # Send in time order
                        dispatch = self.backend_to_app_cache.pop(0)
                        await ws.send(dispatch)

            if is_backend:
                print("Backend connection established")
                # Store the data for sending to the server.
                while True:
                    data = await ws.recv()
                    self.backend_to_app_cache.append(data)
                    self.backend_has_updates.set()

            # async for data in ws:
            #     both_connected = type(self.backend_app) != type(None) and type(self.backend) != type(None)
                
            #     if is_backend:
            #         # Temporary solution to store the configuration 
            #         # TODO Fix this better later
            #         if len(self.backend_to_app_cache) < 10:
            #             self.backend_to_app_cache.append(data)

            #         if both_connected:
            #             await self.backend_app.send(data)
                
            #     if is_app and both_connected:
            #         await self.backend.send(data)

        except websockets.ConnectionClosed:
            print("Connection with [%s] closed: [%s]" % (path, time.time())) 
        finally:
            if is_backend:
                self.backend_to_app_cache = []

"""Start the webserver"""
WebServer()