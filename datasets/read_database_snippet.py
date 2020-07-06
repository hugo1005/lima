import pandas as pd
import sqlite3

conn = sqlite3.connect( 'markets.db')
prices = pd.read_sql('SELECT * FROM prices', conn)
conn.close()

print(prices.tail())