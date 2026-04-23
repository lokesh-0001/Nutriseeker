import pandas as pd

df = pd.read_csv("ifct2017_compositions.csv")

print("Shape:", df.shape)
print("\nColumns:", df.columns.tolist())
print("\nFirst 3 rows:")
print(df.head(3))
print("\nMissing values per column:")
print(df.isnull().sum())
print("\nSample food names:")
print(df['name'].head(20).tolist())