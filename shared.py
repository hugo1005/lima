from collections import namedtuple

LOB = namedtuple('LOB', ['bid_book', 'ask_book', 'best_bid', 'best_ask','bid_depth', 'ask_depth', 'n_bids', 'n_asks', 'bid_volume', 'ask_volume'])

MarketBook = namedtuple('MarketBook', ['bid_book','ask_book'])

CompositionMeta = namedtuple("CompositionMeta", ['weight','price'])

# Note direction is an integer, action is BUY or SELL
ComplexEvent = namedtuple("ComplexEvent", ["lob_condition", "event"])

# A minimal reference to the order
# This is useful for the vuejs frontend to sync optimally with backend feeds
OrderKey = namedtuple('OrderKey', ['ticker', 'order_id', 'order_type', 'action','price'])

OrderSpec = namedtuple('OrderSpec', ['ticker','tid','order_id','order_type','qty','action','price','group'])

# NOTE: tender_ids will have the prefix 'tender_' as their id's must be able to be transacted like regular orders
TenderOrder = namedtuple('TenderOrder', ['ticker','tender_id','qty','action','price','expiration_time'])

ExchangeOrder = namedtuple('ExchangeOrder', ['ticker','tid','order_id','order_type','qty','action','price', 'qty_filled','submission_time'])

ExchangeOrderAnon = namedtuple('ExchangeOrderAnonymised', ['ticker','order_id','order_type','qty','action','price', 'qty_filled'])

Transaction = namedtuple('Transaction', ['tid','order_id','qty','price','timestamp'])

TransactionPair = namedtuple('TransactionPair', ['ticker','action','maker','taker','timestamp'])

TapeTransaction = namedtuple('TapeTransaction', ['ticker','action', 'qty', 'price','timestamp'])

# We avoid deeply nesting named tuples as this can be painful for data transfer
# format of pnl history items {'time':self.get_time(),'value':overall_pnl}

# TickerPnL = namedtuple('TickerPnL', ['ticker','net_position','unrealised','realised','total_pnl', 'total_pnl_history']) # Per Ticker Pnl

TickerPnL = namedtuple('TickerPnL', ['ticker','net_position','unrealised','realised','total_pnl']) # Per Ticker Pnl

# TraderRisk = namedtuple('TraderRisk', ['net_position','gross_position','unrealised','realised','pnl','pnl_history']) # Overall Risk per trader

# NOTE We removed pnl_history as it was compuationally expensive to encode
# pnl history many times for transfer to client
TraderRisk = namedtuple('TraderRisk', ['net_position','gross_position','unrealised','realised','pnl'])

# TickerPNL = namedtuple('TickerPNL', ['buys','sells','realised_points','unrealised_points',])

def cast_named_tuple(tuple_to_cast, cast_to_namedtuple_spec):
    return to_named_tuple(named_tuple_to_dict(tuple_to_cast), cast_to_namedtuple_spec)

def to_named_tuple(json_data, namedtuple_spec):
    fields = namedtuple_spec._fields
    return namedtuple_spec(*[json_data[field] for field in fields])

def update_named_tuple(data, update_dict):
    tuple_type = type(data)
    tuple_dict = dict(data._asdict())

    for key in update_dict:
        tuple_dict[key] = update_dict[key]

    return to_named_tuple(tuple_dict, tuple_type)

def named_tuple_to_dict(data):
    return dict(data._asdict())

def cast_named_tuple_to_dict(tuple_to_cast, cast_to_namedtuple_spec):
    return named_tuple_to_dict(to_named_tuple(named_tuple_to_dict(tuple_to_cast), cast_to_namedtuple_spec))