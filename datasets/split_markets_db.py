import pandas as pd
import matplotlib.pyplot as plt
import sqlite3
import numpy as np
# import mplfinance
import seaborn as sns
from pandas import read_csv

conn = sqlite3.connect('markets_fixed_aws.db')
prices_luno = pd.read_sql('SELECT * FROM prices WHERE exchange = "luno" AND ticker = "XBTEUR"', conn)
prices_kraken = pd.read_sql('SELECT * FROM prices WHERE exchange = "bitstamp" AND ticker = "btceur"', conn)
conn.close()

def clean_prices(df):
    df = df[(df['best_bid'] > 0 ) & (df['best_ask'] > 0) & (df['best_bid'] < 100000) & (df['best_ask'] < 100000)]
    df = df[df['best_ask'] - df['best_bid'] > -5]
    df['timestamp_rounded'] = pd.to_datetime(df['timestamp'].round(0), unit='s')
    df = df.set_index('timestamp_rounded')
    return df
# def create_ohlc(df):
#     return ((df['best_bid'] + df['best_ask'])/2).resample('5Min').ohlc()
prices_luno_clean = clean_prices(prices_luno)
prices_kraken_clean = clean_prices(prices_kraken)
# ohlc_luno = create_ohlc(prices_luno_clean)
# ohlc_kraken = create_ohlc(prices_kraken_clean)
# mplfinance.plot(ohlc_luno,type='candle')
# mplfinance.plot(ohlc_kraken,type='candle')

prices_luno_clean.to_csv('p_luno.csv')
prices_kraken_clean.to_csv('p_kraken.csv') 