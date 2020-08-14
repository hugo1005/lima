from datetime import datetime
import matplotlib.pyplot as plt
import os
import pandas as pd
import sqlite3
from pandas import DataFrame as df
import numpy as np
from pandas import read_csv as rc
import seaborn as sns


def buy_and_sell_entries_S1E(LAhandle,LBhandle,df_general=None):
    # df_general is Best Bid Best Ask for both exchanges
    signalmatrix = df(df_general['lAsk']-df_general['kBid'])
    signalmatrix = signalmatrix.join(df(df_general['lBid']-df_general['kAsk']),rsuffix='r')
    (signalmatrix).columns=('lAkB','lBkA')
    # Our entry and exits
    buyentry=[];sellentry=[]

    # Enter the first buy (Index is zero indexed)
    open_signal = signalmatrix['lAkB']< -LAhandle
    first_entry_idx = df_general[open_signal].head(1).index.values
    buyentry.append(first_entry_idx)

    # Enter the first close
    close_signal = signalmatrix['lBkA']>LBhandle
    first_close_signal = df_general[close_signal] 
    first_close_idx = first_close_signal[first_close_signal.index.values > first_entry_idx].head(1).index.values
    sellentry.append(first_close_idx)

    more_oppurtunities = lambda: len(sellentry[-1])!=0
    trade_initated = lambda: len(buyentry[-1])!=0
    
    while more_oppurtunities():
        next_open_signal = df_general[open_signal]
        next_open_idx = next_open_signal[next_open_signal.index.values > sellentry[-1]].head(1).index.values
        buyentry.append(next_open_idx)
        
        if trade_initated():
            next_close_signal = df_general[close_signal] 
            next_close_idx = next_close_signal[next_close_signal.index.values > next_open_idx].head(1).index.values
            sellentry.append(next_close_idx)
        else:
            break

    # Cleanup the mess 
    for i in [sellentry, buyentry]:
        if len(i[-1])==0:
            i.pop(-1)

    return [buyentry, sellentry]
def trading_plugin_SS2(buysellentries,feesb=0.0025,feess=0.0025,df_price=None):
    
	[buyentry,sellentry]=buysellentries
	Entries=df(buyentry).join(df(sellentry),rsuffix='r')
	Entries.columns=['B','S']

	if len(buyentry)>len(sellentry):
		Entries=Entries.iloc[:(Entries.shape[0]-1),]

	RoT=[None]*(Entries.shape[0])

	for i in range(Entries.shape[0]):
		buyprice=df_price.loc[Entries['B'][i]][2]*(1+feesb)
		sellprice=df_price.loc[Entries['S'][i]][1]*(1-feess)
		RoT[i]=sellprice/buyprice

	Entries_in_time=df(df_price.loc[Entries['B']]['timestamp']).reset_index(
    drop=True).join(df(df_price.loc[Entries['S']]['timestamp']).reset_index(drop=True),rsuffix='S')
	
	Entries_in_time.columns=Entries.columns

	return [Entries_in_time, RoT]



