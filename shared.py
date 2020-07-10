from collections import namedtuple
import warnings

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


# ------------------------------------------------------------------------------------------------------------------------
LunaCreateOrder = namedtuple('LunaCreateOrder', ['id','type','price','volume'])
LunaCreateOrderV2 = namedtuple('LunaCreateOrder', ['order_id','type','price','volume'])
BitstampCreateOrder = namedtuple('BitstampCreateOrder', ['order_id','type','price','qty'])
BitstampCreateOrderV2 = namedtuple('BitstampCreateOrderV2', ['id','order_type','price','amount'])
def LunaToExchangeOrder(ticker, data, submission_time, get_trader_id):
    if 'order_id' in data:
        luna_create_order = to_named_tuple(data, LunaCreateOrderV2)
        action = 'BUY' if luna_create_order.type == 'BID' else 'SELL'
        tid = get_trader_id(luna_create_order.order_id) # Either -1 or one of ours
        return ExchangeOrder(ticker, tid, luna_create_order.order_id, 'LMT', float(luna_create_order.volume), action, float(luna_create_order.price), 0, submission_time)
    else:
        luna_create_order = to_named_tuple(data, LunaCreateOrder)
        action = 'BUY' if luna_create_order.type == 'BID' else 'SELL'
        tid = get_trader_id(luna_create_order.id) # Either -1 or one of ours
        return ExchangeOrder(ticker, tid, luna_create_order.id, 'LMT', float(luna_create_order.volume), action, float(luna_create_order.price), 0, submission_time)

def BitstampToExchangeOrder(ticker, data, submission_time, get_trader_id):
    bitstamp_create_order = to_named_tuple(data, BitstampCreateOrder)
    action = 'BUY' if bitstamp_create_order.type == 'BID' else 'SELL'
    tid = get_trader_id(bitstamp_create_order.order_id)
    return ExchangeOrder(ticker, tid, bitstamp_create_order.order_id, 'LMT', float(bitstamp_create_order.qty), action, float(bitstamp_create_order.price), 0, submission_time)

def BitstampToExchangeOrderV2(ticker, data, submission_time, get_trader_id):
    bitstamp_create_order = to_named_tuple(data, BitstampCreateOrderV2)
    action = 'BUY' if int(bitstamp_create_order.order_type) == 0 else 'SELL'
    tid = get_trader_id(bitstamp_create_order.id)
    order = ExchangeOrder(ticker, tid, bitstamp_create_order.id, 'LMT', float(bitstamp_create_order.amount), action, float(bitstamp_create_order.price), 0, submission_time)
    return order

    
# ------------------------------------------------------------------------------------------------------------------------
KrakenCreateOrder = namedtuple('KrakenCreateOrder', ['order_id','type','price','volume'])

def KrakenToExchangeOrder(ticker, data, submission_time, get_trader_id):
    kraken_create_order = to_named_tuple(data, KrakenCreateOrder)
    action = 'BUY' if kraken_create_order.type == 'BID' else 'SELL'
    tid = get_trader_id(kraken_create_order.order_id) # Either -1 or one of ours

    return ExchangeOrder(ticker, tid, kraken_create_order.order_id, 'LMT', float(kraken_create_order.volume), action, float(kraken_create_order.price), 0, submission_time)

# ------------------------------------------------------------------------------------------------------------------------

ExchangeOrderAnon = namedtuple('ExchangeOrderAnonymised', ['ticker','order_id','order_type','qty','action','price', 'qty_filled'])

Transaction = namedtuple('Transaction', ['tid','order_id','qty','price','timestamp'])

TransactionPair = namedtuple('TransactionPair', ['ticker','action','maker','taker','timestamp'])

TapeTransaction = namedtuple('TapeTransaction', ['ticker','action', 'qty', 'price','timestamp'])

# ------------------------------------------------------------------------------------------------------------------------
LunaTransaction = namedtuple('LunaTransaction', ['base','counter','maker_order_id','taker_order_id'])

def LunaToExchangeTransactionPair(ticker, data, submission_time, get_order_by_id, get_trader_id):
    luna_transaction = to_named_tuple(data, LunaTransaction)
    
    maker_oid = luna_transaction.maker_order_id
    taker_oid = luna_transaction.taker_order_id
    qty_filled = float(luna_transaction.base) # We will always want the base currency quantity cause we only care about how much we spent in the base eg. EUR/BTC with base = EUR

    maker_order = get_order_by_id(maker_oid)
    taker_order = get_order_by_id(taker_oid)

    if type(maker_order) == type(None):
        warnings.warn('Market maker order was not of type LMT or is missing from book, this is very unexpected behaviour!', UserWarning)
        return None
    else:
        action = 'SELL' if maker_order.action == 'BUY' else 'BUY'

        if type(taker_order) == type(None):
            taker_order = ExchangeOrder(ticker, get_trader_id(taker_oid), taker_oid, 'MKT', qty_filled, float(maker_order.price), action, qty_filled, submission_time)

        maker_transaction = Transaction(maker_order.tid, maker_order.order_id, qty_filled, maker_order.price, submission_time)
        taker_transaction = Transaction(taker_order.tid, taker_order.order_id, qty_filled, maker_order.price, submission_time)
        
        transaction_pair =  TransactionPair(ticker, action, maker_transaction, taker_transaction, submission_time)

        return transaction_pair, maker_order, taker_order

# ------------------------------------------------------------------------------------------------------------------------

# We avoid deeply nesting named tuples as this can be painful for data transfer
# format of pnl history items {'time':self.get_time(),'value':overall_pnl}

# TickerPnL = namedtuple('TickerPnL', ['ticker','net_position','unrealised','realised','total_pnl', 'total_pnl_history']) # Per Ticker Pnl

TickerPnL = namedtuple('TickerPnL', ['ticker','net_position','unrealised','realised','total_pnl']) # Per Ticker Pnl

# TraderRisk = namedtuple('TraderRisk', ['net_position','gross_position','unrealised','realised','pnl','pnl_history']) # Overall Risk per trader

# NOTE We removed pnl_history as it was compuationally expensive to encode
# pnl history many times for transfer to client
TraderRisk = namedtuple('TraderRisk', ['net_position','gross_position','unrealised','realised','pnl'])

# TickerPNL = namedtuple('TickerPNL', ['buys','sells','realised_points','unrealised_points',])

RiskLimits = namedtuple('RiskLimits', ['net_position','gross_position'])