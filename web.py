import websockets
import json
import asyncio

class WebServer:
    def __init__(self, config_dir = './configs/frontend_config.json'):
        with open(config_dir) as config_file:
            self.config = json.load(config_file)

        self._port = self.config['app-websocket']['port']
        self._ip = self.config['app-websocket']['ip']
        self.app = None
        self._to_app_cache = []
        self.frontend = None

        self.setup_websocket_server()

    def setup_websocket_server(self):
        print("Initialising websocket...")

        # Initialises the server and ensures it winds down gracefully
        loop = asyncio.get_event_loop()
        handler = websockets.serve(self.bridge, self._ip, self._port)
        server = loop.run_until_complete(handler)

        loop.run_forever()

        # Close the server
        server.close()
        loop.run_until_complete(server.wait_closed())
    
    async def bridge(self, ws, path):
        is_frontend, is_app = path == '/frontend', path == '/app'

        # Register connection
        if is_frontend:
            print("Frontend connection established")
            self.frontend = ws
        elif is_app:
            print("App connection established")
            self.app = ws
        else:
            print("Websocket path unkown: %s" % path)
        
        try:
            if is_app: # Replay all messages to catch up
                for data in self._to_app_cache:
                    await self.app.send(data)

            async for data in ws:
                both_connected = type(self.app) != type(None) and type(self.frontend) != type(None)
                if both_connected:
                    if is_frontend:
                        self._to_app_cache.append(data)
                        await self.app.send(data)
                    elif is_app:
                        await self.frontend.send(data)

        except websockets.ConnectionClosed:
            print("Connection with [%s] closed" % path) 
        finally:
            if is_frontend: 
                self.frontend = None
                self._to_app_cache = [] # Clear the message cache
            if is_app: self.app = None

"""Start the webserver"""
WebServer()