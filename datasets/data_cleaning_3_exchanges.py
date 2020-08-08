from datetime import datetime

import matplotlib.pyplot as plt
import os
import pandas as pd
import sqlite3
from pandas import DataFrame as df
import numpy as np
from pandas import read_csv as rc

def clean_prices(df):
    df = df[(df['best_bid'] > 0) & (df['best_ask'] > 0) & (df['best_bid'] < 100000) & (df['best_ask'] < 100000)]
    df = df[df['best_ask'] - df['best_bid'] > -5]
    df['timestamp_rounded'] = pd.to_datetime(df['timestamp'].round(0), unit='s')
    df = df.set_index('timestamp_rounded')
    return df

def makearray(pindex, tl):
    timearray=[]
    y=str(pindex[0])[5:tl]
    timearray.append(y)
    i0=0
    indexarrayL=[i0]

    for x in pindex:
        if y!=str(x)[5:tl]:
            timearray.append(str(x)[5:tl])  # change to 16 to 19 to make it in seconds
            indexarrayL.append(i0)
            y=str(x)[5:tl]
        i0+=1
    return [indexarrayL,timearray]

tl = 19  # use 19 for seconds, 16 is for minutes
relevant_cols = ['timestamp_rounded', 'timestamp', 'best_bid', 'best_ask']

# BTC/EUR
pl=rc('p_luno_btc_eur_v1.csv', usecols=relevant_cols)
pk=rc('p_kraken_btc_eur_v1.csv', usecols=relevant_cols)
pb=rc('p_bitstamp_btc_eur_v1.csv', usecols=relevant_cols)
pl = pl.set_index('timestamp_rounded')
pk = pk.set_index('timestamp_rounded')
pb = pb.set_index('timestamp_rounded')

# the datasets were already cleaned, so we do not need to run clean_prices

indexarrayL, timearrayL = makearray(pl.index, tl)
indexarrayK, timearrayK = makearray(pk.index, tl)
indexarrayB, timearrayB = makearray(pb.index, tl)

mergeddf=df(columns=['Time', 'kBid', 'kAsk', 'bBid', 'bAsk', 'lBid','lAsk'])

num_iters = len(indexarrayL)
print('Number of iterations: ' + str(num_iters))
iter_counter = 0

for i in indexarrayL:
    i=pl.index[i]
    if type(pl.loc[i,'best_bid'])==pd.core.series.Series:
        mergeddf=mergeddf.append({'Time': str(i)[5:tl], 'lBid':pl.loc[i,'best_bid'].values[0],'lAsk':pl.loc[i,'best_ask'].values[0]}, ignore_index=True)
    else:
        mergeddf=mergeddf.append({'Time': str(i)[5:tl], 'lBid':pl.loc[i,'best_bid'],'lAsk':pl.loc[i,'best_ask']}, ignore_index=True)

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))
    
mergeddf=mergeddf.set_index('Time')

num_iters = len(set(timearrayL).intersection(set(timearrayK)))
print('Number of iterations: ' + str(num_iters))
iter_counter = 0
k_index = 0

for i in sorted(set(timearrayL).intersection(set(timearrayK))):
    while str(pk.index[indexarrayK[k_index]])[5:tl] < i:
        k_index += 1
    k=pk.index[indexarrayK[k_index]]
    if type(pk.loc[k,'best_bid'])==pd.core.series.Series:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'].values[0],pk.loc[k,'best_ask'].values[0] ]
    else:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'],pk.loc[k,'best_ask'] ]

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))

num_iters = len(set(timearrayL).intersection(set(timearrayB)))
print('Number of iterations: ' + str(num_iters))
iter_counter = 0
b_index = 0

for i in sorted(set(timearrayL).intersection(set(timearrayB))):
    while str(pb.index[indexarrayB[b_index]])[5:tl] < i:
        b_index += 1
    b=pb.index[indexarrayB[b_index]]
    if type(pb.loc[b,'best_bid'])==pd.core.series.Series:
        mergeddf.loc[i][2:4]=[pb.loc[b,'best_bid'].values[0],pb.loc[b,'best_ask'].values[0] ]
    else:
        mergeddf.loc[i][2:4]=[pb.loc[b,'best_bid'],pb.loc[b,'best_ask'] ]

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))

mergeddf.to_csv('merged_btc_eur_sec.csv')

# BTC/GBP
pl=rc('p_luno_btc_gbp_v1.csv', usecols=relevant_cols)
pk=rc('p_kraken_btc_gbp_v1.csv', usecols=relevant_cols)
pb=rc('p_bitstamp_btc_gbp_v1.csv', usecols=relevant_cols)
pl = pl.set_index('timestamp_rounded')
pk = pk.set_index('timestamp_rounded')
pb = pb.set_index('timestamp_rounded')

# the datasets were already cleaned, so we do not need to run clean_prices

indexarrayL, timearrayL = makearray(pl.index, tl)
indexarrayK, timearrayK = makearray(pk.index, tl)
indexarrayB, timearrayB = makearray(pb.index, tl)

mergeddf=df(columns=['Time', 'kBid', 'kAsk', 'bBid', 'bAsk', 'lBid','lAsk'])

num_iters = len(indexarrayL)
print('Number of iterations: ' + str(num_iters))
iter_counter = 0

for i in indexarrayL:
    i=pl.index[i]
    if type(pl.loc[i,'best_bid'])==pd.core.series.Series:
        mergeddf=mergeddf.append({'Time': str(i)[5:tl], 'lBid':pl.loc[i,'best_bid'].values[0],'lAsk':pl.loc[i,'best_ask'].values[0]}, ignore_index=True)
    else:
        mergeddf=mergeddf.append({'Time': str(i)[5:tl], 'lBid':pl.loc[i,'best_bid'],'lAsk':pl.loc[i,'best_ask']}, ignore_index=True)

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))
    
mergeddf=mergeddf.set_index('Time')

num_iters = len(set(timearrayL).intersection(set(timearrayK)))
print('Number of iterations: ' + str(num_iters))
iter_counter = 0
k_index = 0

for i in sorted(set(timearrayL).intersection(set(timearrayK))):
    while str(pk.index[indexarrayK[k_index]])[5:tl] < i:
        k_index += 1
    k=pk.index[indexarrayK[k_index]]
    if type(pk.loc[k,'best_bid'])==pd.core.series.Series:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'].values[0],pk.loc[k,'best_ask'].values[0] ]
    else:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'],pk.loc[k,'best_ask'] ]

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))

num_iters = len(set(timearrayL).intersection(set(timearrayB)))
print('Number of iterations: ' + str(num_iters))
iter_counter = 0
b_index = 0

for i in sorted(set(timearrayL).intersection(set(timearrayB))):
    while str(pb.index[indexarrayB[b_index]])[5:tl] < i:
        b_index += 1
    b=pb.index[indexarrayB[b_index]]
    if type(pb.loc[b,'best_bid'])==pd.core.series.Series:
        mergeddf.loc[i][2:4]=[pb.loc[b,'best_bid'].values[0],pb.loc[b,'best_ask'].values[0] ]
    else:
        mergeddf.loc[i][2:4]=[pb.loc[b,'best_bid'],pb.loc[b,'best_ask'] ]

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))

mergeddf.to_csv('merged_btc_gbp_sec.csv')