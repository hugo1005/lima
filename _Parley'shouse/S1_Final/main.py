from datetime import datetime
import matplotlib.pyplot as plt
import os
import pandas as pd
import sqlite3
from pandas import DataFrame as df
import numpy as np
from pandas import read_csv as rc

df_general=rc('Copy of merged_large_2_min.csv')

#Housekeeping
df_general=df_general.ffill()
signalmatrix=df(df_general['lBid']-df_general['kBid'])
signalmatrix=signalmatrix.join(df(df_general['lAsk']-df_general['kAsk']),rsuffix='r')
(signalmatrix).columns=('BidDiff','AskDiff')

exec(open("S1_General.py").read())

timeindf,RoT=trading_plugin(buy_and_sell_entries(20,10))

timeindf['RoT']=RoT