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

# check if deribit has the ones from luno:
relevant_symbol_ids_dct_db = []

for symbol_ids_dct in symbol_ids_dct_list:
    if 'DERIBIT_SPOT_BTC_IDR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'DERIBIT_SPOT_BTC_MYR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'DERIBIT_SPOT_BTC_NGN' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'DERIBIT_SPOT_BTC_ZAR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct_db:
    print(e['symbol_id'])

# this did not find anything

# look what is available

relevant_symbol_ids_dct_db = []

for symbol_ids_dct in symbol_ids_dct_list:
    if 'DERIBIT_' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct_db:
    print(e['symbol_id'])

for e in relevant_symbol_ids_dct_db:
    if 'DERIBIT_OPT' not in e['symbol_id']:
        print(e['symbol_id'])

# DERIBIT_PERP_BTC_USD
# DERIBIT_PERP_ETH_USD
# DERIBIT_FTS_ETH_USD_200327
# DERIBIT_FTS_BTC_USD_200327
# ...
# DERIBIT_FTS_BTC_USD_170324
# DERIBIT_FTS_BTC_USD_190315
# DERIBIT_FTS_BTC_USD_170317

# apparently deribit has only options, perpetual and futures - no spot

# now look at kraken
relevant_symbol_ids_dct_kr = []

for e in relevant_symbol_ids_dct_kr:
    print(e['symbol_id'])
    if 'KRAKEN_SPOT_BTC_IDR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'KRAKEN_SPOT_BTC_MYR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'KRAKEN_SPOT_BTC_NGN' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)
    if 'KRAKEN_SPOT_BTC_ZAR' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_db.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct_kr:
    print(e['symbol_id'])

# returned nothing...

relevant_symbol_ids_dct_kr = []

for symbol_ids_dct in symbol_ids_dct_list:
    if 'KRAKEN_SPOT_BTC' in symbol_ids_dct['symbol_id']:
        relevant_symbol_ids_dct_kr.append(symbol_ids_dct)

for e in relevant_symbol_ids_dct_kr:
    print(e['symbol_id'])

# KRAKEN_SPOT_BTC_USD
# KRAKEN_SPOT_BTC_EUR
# KRAKEN_SPOT_BTC_GBP
# KRAKEN_SPOT_BTC_JPY
# KRAKEN_SPOT_BTC_CAD
# KRAKEN_SPOT_BTC_XRP
# KRAKEN_SPOT_BTC_LTC
# KRAKEN_SPOT_BTC_NMC
# KRAKEN_SPOT_BTC_VEN
# KRAKEN_SPOT_BTC_DOGE
# KRAKEN_SPOT_BTC_KST
# KRAKEN_SPOT_BTC_KRW
# KRAKEN_SPOT_BTC_CHF
# KRAKEN_SPOT_BTC_DAI
# KRAKEN_SPOT_BTC_USDT
# KRAKEN_SPOT_BTC_USDC
# KRAKEN_SPOT_BTC_XLM
# KRAKEN_SPOT_BTC_CAD_5641E1
# KRAKEN_SPOT_BTC_EUR_5641E2
# KRAKEN_SPOT_BTC_CHF_57CCC4
# KRAKEN_SPOT_BTC_DAI_57CCC8
# KRAKEN_SPOT_BTC_USDC_57CCCC
# KRAKEN_SPOT_BTC_USDT_57CCCF
# KRAKEN_SPOT_BTC_CAD_57CD12
# KRAKEN_SPOT_BTC_EUR_57CD16
# KRAKEN_SPOT_BTC_GBP_57CD19
# KRAKEN_SPOT_BTC_JPY_57CD1C
# KRAKEN_SPOT_BTC_USD_57CD20

# unfortunately no overlap with Luno...

# let's check now which exchanges have ones which overlap with luno

# LUNO_SPOT_BTC_IDR
# LUNO_SPOT_BTC_MYR
# LUNO_SPOT_BTC_NGN
# LUNO_SPOT_BTC_ZAR

target_combinations = ['SPOT_BTC_IDR', 'SPOT_BTC_MYR', 'SPOT_BTC_NGN', 'SPOT_BTC_ZAR']

for combination in target_combinations:
    print('Searching for ' + combination)
    relevant_symbol_ids_dct_tmp = []
    for symbol_ids_dct in symbol_ids_dct_list:
        if combination in symbol_ids_dct['symbol_id']:
            relevant_symbol_ids_dct_tmp.append(symbol_ids_dct)
    for e in relevant_symbol_ids_dct_tmp:
        print(e['symbol_id'])

# Searching for SPOT_BTC_IDR
# LUNO_SPOT_BTC_IDR
# BITCOINID_SPOT_BTC_IDR
# QUOINE_SPOT_BTC_IDR
# INDODAX_SPOT_BTC_IDR
# QUOINE_SPOT_BTC_IDRT
# BINANCE_SPOT_BTC_IDRT
# EXRATES_SPOT_BTC_IDR
# HUOBIIND_SPOT_BTC_IDR
# TRIVPRO_SPOT_BTC_IDR
# BISQ_SPOT_BTC_IDR
# STELLARPORT_SPOT_BTC_IDR

# Searching for SPOT_BTC_MYR
# LUNO_SPOT_BTC_MYR
# BISQ_SPOT_BTC_MYR
# COINUT_SPOT_BTC_MYR

# Searching for SPOT_BTC_NGN
# LUNO_SPOT_BTC_NGN
# ICE3X_SPOT_BTC_NGN
# BINANCE_SPOT_BTC_NGN
# STELLARPORT_SPOT_BTC_NGNT
# BISQ_SPOT_BTC_NGN
# STELLARPORT_SPOT_BTC_NGNX
# EXRATES_SPOT_BTC_NGN
# LOCALTRADE_SPOT_BTC_NGN

# Searching for SPOT_BTC_ZAR
# LUNO_SPOT_BTC_ZAR
# 1BTCXE_SPOT_BTC_ZAR
# ALTCOINTRADER_SPOT_BTC_ZAR
# ICE3X_SPOT_BTC_ZAR
# STELLARPORT_SPOT_BTC_ZAR
# BISQ_SPOT_BTC_ZAR
# BINANCE_SPOT_BTC_ZAR
# ARTISTURBA_SPOT_BTC_ZAR
# STELLARPORT_SPOT_BTC_ZART
# OVEX_SPOT_BTC_ZAR

# how we would get historical data: https://docs.coinapi.io/?python#historical-data42

# get historical data: /v1/orderbooks/{symbol_id}/history?time_start={time_start}&time_end={time_end}&limit={limit}&limit_levels={limit_levels}

# url = 'https://rest.coinapi.io/v1/orderbooks/BITSTAMP_SPOT_BTC_USD/history?time_start=2016-01-01T00:00:00'
# headers = {'X-CoinAPI-Key' : api_key}
# response = requests.get(url, headers=headers)

# print(response.json())