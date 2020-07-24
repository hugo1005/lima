from datetime import datetime

import matplotlib.pyplot as plt
import os
import pandas as pd
import sqlite3
from pandas import DataFrame as df
import numpy as np
from pandas import read_csv as rc

def clean_prices(df):
    df = df[(df['best_bid'] > 100) & (df['best_ask'] > 100) & (df['best_bid'] < 100000) & (df['best_ask'] < 100000)]
    df = df[df['best_ask'] - df['best_bid'] > -5]
    df['timestamp_rounded'] = pd.to_datetime(df['timestamp'].round(0), unit='s')
    df = df.set_index('timestamp_rounded')
    return df

def makearray(pindex):
    timearray=[]
    y=str(pindex[0])[5:16]
    timearray.append(y)
    i0=0
    indexarrayL=[i0]

    for x in pindex:
        if y!=str(x)[5:16]:
            timearray.append(str(x)[5:16])
            indexarrayL.append(i0)
            y=str(x)[5:16]
        i0+=1
    return [indexarrayL,timearray]


pl=rc('p_luno_large.csv')
pk=rc('p_kraken_large.csv')

# pk=clean_prices(pkraken)
# pl=clean_prices(pluno)
# it was already cleaned - just the lower boundary was 0 instead of 100, but that should not matter

indexarrayL, timearrayL = makearray(pl.index)
indexarrayK, timearrayK = makearray(pk.index)

mergeddf=df(columns=['Time', 'kBid', 'kAsk','lBid','lAsk'])

num_iters = len(indexarrayL)
print('Number of iterations: ' + str(num_iters))
iter_counter = 0

# for i in indexarrayL:
#     i=pl.index[i]
#     if type(pl.loc[i,'best_bid'])==pd.core.series.Series:
#         mergeddf=mergeddf.append({'Time': str(i)[5:16], 'lBid':pl.loc[i,'best_bid'].values[0],'lAsk':pl.loc[i,'best_ask'].values[0]}, ignore_index=True)
#     else:
#         mergeddf=mergeddf.append({'Time': str(i)[5:16], 'lBid':pl.loc[i,'best_bid'],'lAsk':pl.loc[i,'best_ask']}, ignore_index=True)

#     iter_counter += 1
#     if iter_counter % 1000 == 0:
#         print(str(iter_counter) + '/' + str(num_iters))
    

# mergeddf=mergeddf.set_index('Time')

num_iters = len(set(timearrayL).intersection(set(timearrayK)))
print('Number of iterations: ' + str(num_iters))
iter_counter = 0

for i in set(timearrayL).intersection(set(timearrayK)):
    for k in indexarrayK:
        if str(pk.index[k])[5:16]==i:
            break
    k=pk.index[k]
    if type(pk.loc[k,'best_bid'])==pd.core.series.Series:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'].values[0],pk.loc[k,'best_ask'].values[0] ]
    else:
        mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'],pk.loc[k,'best_ask'] ]

    iter_counter += 1
    if iter_counter % 1000 == 0:
        print(str(iter_counter) + '/' + str(num_iters))

#  mergeddf.loc[i][0:2]=[,]

mergeddf.to_csv('merged_large.csv')