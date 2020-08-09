import pandas as pd
import matplotlib.pyplot as plt
import sqlite3
import numpy as np
import seaborn as sns
from pandas import read_csv

def clean_prices(df):
    df = df[(df['best_bid'] > 0 ) & (df['best_ask'] > 0) & (df['best_bid'] < 100000) & (df['best_ask'] < 100000)]
    df = df[df['best_ask'] - df['best_bid'] > -5]
    df['timestamp_rounded'] = pd.to_datetime(df['timestamp'].round(0), unit='s')
    df = df.set_index('timestamp_rounded')
    return df


# large datasets do not fit into memory - need to do it in chunks
# chunksize of 1000000 (1 million) is about 200 MB

# unify the timestamp so that it is all for the same period - when did I deploy it?
# 2020-7-30-02:00:00 GMT - it should have started by then
# 1596074400

# original cutoff was 1594940000

# BTC/EUR

# luno
conn = sqlite3.connect('markets_btceur_7aug2020.db')
prices_luno = pd.read_sql('SELECT * FROM prices WHERE exchange = "luno" AND ticker = "XBTEUR" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_luno_chunk in prices_luno:
    prices_luno_clean = clean_prices(prices_luno_chunk)
    prices_luno_clean.to_csv('p_luno_btc_eur_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Luno processed')

# bitstamp
conn = sqlite3.connect('markets_btceur_7aug2020.db')
prices_bitstamp = pd.read_sql('SELECT * FROM prices WHERE exchange = "bitstamp" AND ticker = "btceur" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_bitstamp_chunk in prices_bitstamp:
    prices_bitstamp_clean = clean_prices(prices_bitstamp_chunk)
    prices_bitstamp_clean.to_csv('p_bitstamp_btc_eur_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Bitstamp processed')

# kraken
conn = sqlite3.connect('markets_btceur_7aug2020.db')
prices_kraken = pd.read_sql('SELECT * FROM prices WHERE exchange = "kraken" AND ticker = "XBTEUR" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_kraken_chunk in prices_kraken:
    prices_kraken_clean = clean_prices(prices_kraken_chunk)
    prices_kraken_clean.to_csv('p_kraken_btc_eur_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Kraken processed')

# globitex
conn = sqlite3.connect('markets_btceur_7aug2020.db')
prices_globitex = pd.read_sql('SELECT * FROM prices WHERE exchange = "globitex" AND ticker = "BTCEUR" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_globitex_chunk in prices_globitex:
    prices_globitex_clean = clean_prices(prices_globitex_chunk)
    prices_globitex_clean.to_csv('p_globitex_btc_eur_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Globitex processed')

print('BTC/EUR processed')

# BTC/GBP
# This has no Globitex - but we can run it just in case

# luno
conn = sqlite3.connect('markets_btcgbp_7aug2020.db')
prices_luno = pd.read_sql('SELECT * FROM prices WHERE exchange = "luno" AND ticker = "XBTGBP" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_luno_chunk in prices_luno:
    prices_luno_clean = clean_prices(prices_luno_chunk)
    prices_luno_clean.to_csv('p_luno_btc_gbp_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Luno processed')

# bitstamp
conn = sqlite3.connect('markets_btcgbp_7aug2020.db')
prices_bitstamp = pd.read_sql('SELECT * FROM prices WHERE exchange = "bitstamp" AND ticker = "btcgbp" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_bitstamp_chunk in prices_bitstamp:
    prices_bitstamp_clean = clean_prices(prices_bitstamp_chunk)
    prices_bitstamp_clean.to_csv('p_bitstamp_btc_gbp_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Bitstamp processed')

# kraken
conn = sqlite3.connect('markets_btcgbp_7aug2020.db')
prices_kraken = pd.read_sql('SELECT * FROM prices WHERE exchange = "kraken" AND ticker = "XBTGBP" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_kraken_chunk in prices_kraken:
    prices_kraken_clean = clean_prices(prices_kraken_chunk)
    prices_kraken_clean.to_csv('p_kraken_btc_gbp_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Kraken processed')

# globitex
conn = sqlite3.connect('markets_btcgbp_7aug2020.db')
prices_globitex = pd.read_sql('SELECT * FROM prices WHERE exchange = "globitex" AND ticker = "BTCGBP" AND timestamp > 1596074400', conn, chunksize=2000000)
header = True
for prices_globitex_chunk in prices_globitex:
    prices_globitex_clean = clean_prices(prices_globitex_chunk)
    prices_globitex_clean.to_csv('p_globitex_btc_gbp_v1.csv', header=header, mode='a')
    header = False

conn.close()

print('Globitex processed')

print('BTC/GBP processed')