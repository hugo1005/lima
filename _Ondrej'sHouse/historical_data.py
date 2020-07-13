import requests

# here we get some historical data to perform analysis
api_key = '93E4B0FE-5A23-456C-A8E2-FE04A9EC22D7'
# email = 'tsofgygbbxnzwrbtoi@ttirv.org'

# available symbols for luno and bitstamp

url = 'https://rest.coinapi.io/v1/symbols'
headers = {'X-CoinAPI-Key' : api_key, 'filter_symbol_id': 'LUNO'}
response = requests.get(url, headers=headers)

symbol_ids_dct_list = response.json()

relevant_symbol_ids_dct = []

for symbol_ids_dct in symbol_ids_dct_list:
    if 'LUNO' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct:
    print(e['symbol_id'])

# LUNO_SPOT_BTC_IDR
# LUNO_SPOT_BTC_MYR
# LUNO_SPOT_BTC_NGN
# LUNO_SPOT_BTC_ZAR

relevant_symbol_ids_dct_bs = []

for symbol_ids_dct in symbol_ids_dct_list:
    if 'BITSTAMP' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_bs.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct_bs:
    print(e['symbol_id'])

# BITSTAMP_SPOT_BTC_USD
# BITSTAMP_SPOT_BTC_EUR
# BITSTAMP_SPOT_EUR_USD
# BITSTAMP_SPOT_XRP_EUR
# BITSTAMP_SPOT_XRP_USD
# BITSTAMP_SPOT_XRP_BTC
# BITSTAMP_SPOT_LTC_USD
# BITSTAMP_SPOT_LTC_EUR
# BITSTAMP_SPOT_LTC_BTC
# BITSTAMP_SPOT_ETH_BTC
# BITSTAMP_SPOT_ETH_EUR
# BITSTAMP_SPOT_ETH_USD
# BITSTAMP_SPOT_BCH_BTC
# BITSTAMP_SPOT_BCH_EUR
# BITSTAMP_SPOT_BCH_USD

# this does not seem to be very helpful...

# how we would get historical data: https://docs.coinapi.io/?python#historical-data42

# get historical data: /v1/orderbooks/{symbol_id}/history?time_start={time_start}&time_end={time_end}&limit={limit}&limit_levels={limit_levels}

# url = 'https://rest.coinapi.io/v1/orderbooks/BITSTAMP_SPOT_BTC_USD/history?time_start=2016-01-01T00:00:00'
# headers = {'X-CoinAPI-Key' : api_key}
# response = requests.get(url, headers=headers)

# print(response.json())