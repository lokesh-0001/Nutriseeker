import pandas as pd

df = pd.read_csv('ifct2017_compositions.csv')
carrot = df[df['name'].str.contains('arrot', case=False, na=False)]
print(carrot[['name', 'na', 'ca', 'fe', 'vitc', 'k', 'mg', 'zn']].to_string())