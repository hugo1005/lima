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

pl=rc('p_luno_large_2.csv')
pk=rc('p_kraken_large_2.csv')
pl = pl.set_index('timestamp_rounded')
pk = pk.set_index('timestamp_rounded')

# pk=clean_prices(pkraken)
# pl=clean_prices(pluno)
# it was already cleaned - just the lower boundary was 0 instead of 100, but that should not matter

indexarrayL, timearrayL = makearray(pl.index, tl)
indexarrayK, timearrayK = makearray(pk.index, tl)

mergeddf=df(columns=['Time', 'kBid', 'kAsk','lBid','lAsk'])

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

# num_iters = len(set(timearrayL).intersection(set(timearrayK)))
# print('Number of iterations: ' + str(num_iters))
# iter_counter = 0

# for i in set(timearrayL).intersection(set(timearrayK)):
#     for k in indexarrayK:
#         if str(pk.index[k])[5:tl]==i:
#             break
#     k=pk.index[k]
#     if type(pk.loc[k,'best_bid'])==pd.core.series.Series:
#         mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'].values[0],pk.loc[k,'best_ask'].values[0] ]
#     else:
#         mergeddf.loc[i][0:2]=[pk.loc[k,'best_bid'],pk.loc[k,'best_ask'] ]

#     iter_counter += 1
#     if iter_counter % 1000 == 0:
#         print(str(iter_counter) + '/' + str(num_iters))

# #  mergeddf.loc[i][0:2]=[,]

# mergeddf.to_csv('merged_large_sec.csv')

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

#  mergeddf.loc[i][0:2]=[,]

mergeddf.to_csv('merged_large_2_sec.csv')  # called merged_large_2.csv for minute data

# checked if the new way gives the same results as the first way
# >>> a = pd.read_csv('merged_large_2.csv')
# >>> b = pd.read_csv('merged_large.csv')
# >>> a == b
#       Time  kBid  kAsk  lBid  lAsk
# 0     True  True  True  True  True
# 1     True  True  True  True  True
# 2     True  True  True  True  True
# 3     True  True  True  True  True
# 4     True  True  True  True  True
# ...    ...   ...   ...   ...   ...
# 9953  True  True  True  True  True
# 9954  True  True  True  True  True
# 9955  True  True  True  True  True
# 9956  True  True  True  True  True
# 9957  True  True  True  True  True

# [9958 rows x 5 columns]
# it seems correct