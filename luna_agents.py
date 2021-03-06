from traders import StatArbTrader
import asyncio
import json

class MarketAgentsManager():
    def __init__(self, config_dir='./configs/backend_config.json'):
        
        with open(config_dir) as config_file:
            self._config = json.load(config_file)
        
        self._exchange_name = self._config['exchanges']['active_case']
        self._market_agents_config = self._config['exchanges'][self._exchange_name]["market_agents"]
        self._agents = []

    async def create_agents(self):
        self._agents += [LunaTrader()]    
        trader_activations = asyncio.gather(*[t.connect() for t in self._agents])
        print("Activating automated traders...")
        await asyncio.gather(trader_activations)


"""
Create agents
"""

agents_manager = MarketAgentsManager()
loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.gather(agents_manager.create_agents()))

