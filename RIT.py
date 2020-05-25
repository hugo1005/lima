from collections import namedtuple
from shared import *
# RIT_LOB = namedtuple('RIT_LOB', ['bid_book', 'ask_book', 'best_bid', 'best_ask','bid_depth', 'ask_depth', 'n_bids', 'n_asks', 'bid_volume', 'ask_volume'])

class RITBridge:
    """
    Handles all mapping and bridging to LIMA Api
    """

    def __init__(self):
        # Here we simply define how to map
        # There are going to be additional functions which are more intelligent
        # which will be able to impute missing values accurately noted by missing, and TODO

        # --------------------------------- Converting data feed from RIT to LIMA ----------------------------------
        # ++++ Order Mappings ++++
        RITExchangeOrder = namedtuple('RITExchangeOrder', ['order_id', 'period', 'tick', 'trader_id', 'ticker', 'type', 'quantity', 'action', 'price', 'quantity_filled', 'vwap', 'status'])

        # NOTE We don't need VWAP, Status, Period, Tick from RIT
        # TODO We must track submission_time internally as RIT isn't accurate
        # However it is not too important for now as we only use submission time for building a price time priority queue. So we can use the ordering in which they are returned to impute the true time of entry
        ExchangeOrderMapToLima = named_tuple_to_dict(RITExchangeOrder('order_id', None, None, 'tid', 'ticker', 'order_type', 'qty', 'action', 'price', 'quantity_filled', None, 'tick'))
        
        # ++++ Transactions ++++
        RITTapeTransaction = namedtuple('RITTapeTransaction', ['id', 'period', 'tick', 'price', 'quantity'])
        
        # NOTE We don't need Period
        # TODO The tick and id represent a way to compute the true transaction time, 
        # ie. count the number of transactions that occur in a given tick and assign them equally distant time 
        # increments in the range [tick, tick + 1) in increasing order id.
        # TODO We can infer the ticker from our API call which requires the ticker to be specified
        # TODO We can infer the action (of the liquidity taker) by some clever hueristic we i need to think about 
        TapeTransactionMapToLima = named_tuple_to_dict(RITTapeTransaction(None, None, None, 'price', 'quantity'))

        # ++++ Book ++++
        RITLOB = namedtuple('RITLOB', ['bid','ask'])

        # TODO They have an unheloful format for the book so we will need to convert both books
        # TODO Impute all the missing values detailed below.
        RITLOBMapToLima = named_tuple_to_dict(RITLOB('bid_book', 'ask_book'))

        # NOTE No Market Book is available 

        # NOTE No TransactionPair or Transaction is available but we should be able to impute these

        # Mappings Dict from type to 
        self.mappings = {
            RITExchangeOrder: {'key_map': ExchangeOrderMapToLima, 'named_tuple': ExchangeOrder, 'missing':[]},
            RITTapeTransaction: {'key_map': TapeTransactionMapToLima, 'named_tuple': TapeTransaction, 'missing':['ticker','action','timestamp']},
            RITLOB: {'key_map': RITLOBMapToLima, 'named_tuple': LOB, 'missing':['best_bid', 'best_ask','bid_depth', 'ask_depth', 'n_bids', 'n_asks', 'bid_volume', 'ask_volume']}
        }

        

    def map_RIT_to_Lima(self, to_map):
        """
        Converts named tuple in RIT to a given mapping in Lima as a namedtuple
        """
        # Dictionary of namedtuple instace from RIT
        RIT_values_dict = named_tuple_to_dict(to_map)
        named_tuple_type = type(to_map)

        # All the details of how to map to its Lima equivalent
        mapper_obj = self.mappings[named_tuple_type]
        
        key_map = mapper_obj['key_map'] # From RIT Key -> to Lima Key
        convert_to = mapper_obj['named_tuple'] # The named tuple Lima equivalent
        missing = mapper_obj['missing']  # The keys which are not in RIT but are in Lima : Value is the function and args to get them

        # Renames RIT keys as Lima Keys and maps the values accross
        mapped_dict = {key_map[key]: value for key, value in RIT_values_dict.items()}

        # For all missing lima keys assign a value of None
        for missing_value in missing:
            mapped_dict[missing_value] = None

        lima_tuple = to_named_tuple(mapped_dict, convert_to)
        
        return lima_tuple
