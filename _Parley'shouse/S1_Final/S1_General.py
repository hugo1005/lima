def buy_and_sell_entries(ADhandle,BDhandle,df_general=df_general,signalmatrix=signalmatrix):

	buyentry=[];sellentry=[]
	buyentry.append(df_general[signalmatrix['AskDiff']<-ADhandle].head(1).index.values)
	sellentry.append(df_general[signalmatrix['BidDiff']>BDhandle][
	    df_general[signalmatrix['BidDiff']>BDhandle].index.values>buyentry[-1]].head(1).index.values)

	while len(sellentry[-1])!=0:
	  buyentry.append(df_general[signalmatrix['AskDiff']<-ADhandle][
	    df_general[signalmatrix['AskDiff']<-ADhandle].index.values>sellentry[-1]].head(1).index.values)
	  if len(buyentry[-1])!=0:
	    sellentry.append(df_general[signalmatrix['BidDiff']>BDhandle][
	        df_general[signalmatrix['BidDiff']>BDhandle].index.values>buyentry[-1]].head(1).index.values)
	  else:
	    break

	for i in [sellentry, buyentry]:
	  if len(i[-1])==0:
	    i.pop(-1)

	return [buyentry, sellentry]


def trading_plugin(buysellentries):
	[buyentry,sellentry]=buysellentries
	Entries=df(buyentry).join(df(sellentry),rsuffix='r')
	Entries.columns=['B','S']

	if len(buyentry)>len(sellentry):
		Entries=Entries.iloc[:(Entries.shape[0]-1),]

	RoT=[None]*(Entries.shape[0])

	for i in range(Entries.shape[0]):
		buyprice=df_general.loc[Entries['B'][i]][4]
		sellprice=df_general.loc[Entries['S'][i]][3]
		RoT[i]=sellprice/buyprice

	Entries_in_time=df(df_general.loc[Entries['B']]['Time']).reset_index(
    drop=True).join(
	df(df_general.loc[Entries['S']]['Time']).reset_index(drop=True),rsuffix='S')
	Entries_in_time.columns=Entries.columns

	return [Entries_in_time,RoT]