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

# luno
conn = sqlite3.connect('markets_2_cp.db')
prices_luno = pd.read_sql('SELECT * FROM prices WHERE exchange = "luno" AND ticker = "XBTEUR" AND timestamp > 1594940000', conn, chunksize=1000000)
header = True
for prices_luno_chunk in prices_luno:
    prices_luno_clean = clean_prices(prices_luno_chunk)
    prices_luno_clean.to_csv('p_luno_large.csv', header=header, mode='a')
    header = False

conn.close()

print('Luno processed')

# kraken
conn = sqlite3.connect('markets_2_cp.db')
prices_kraken = pd.read_sql('SELECT * FROM prices WHERE exchange = "bitstamp" AND ticker = "btceur" AND timestamp > 1594940000', conn, chunksize=1000000)
header = True
for prices_kraken_chunk in prices_kraken:
    prices_kraken_clean = clean_prices(prices_kraken_chunk)
    prices_kraken_clean.to_csv('p_kraken_large.csv', header=header, mode='a')
    header = False

conn.close()

print('Kraken processed')