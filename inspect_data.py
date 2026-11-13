"""Quick inspection of the raw Zomato dataset (step 3)."""

import pandas as pd

# Read the restaurants CSV (the file uses latin-1 encoding, not UTF-8)
restaurants = pd.read_csv("data/zomato.csv", encoding="latin-1")

# Read the country code Excel file
countries = pd.read_excel("data/Country-Code.xlsx")

# Show the shape (rows, columns) of both tables
print("Restaurants shape:", restaurants.shape)
print("Countries shape:", countries.shape)

# Show the column names and their data types
print("\nRestaurant columns:")
print(restaurants.dtypes)

# Show the first 3 rows of each table
print("\nFirst rows of restaurants:")
print(restaurants.head(3).T)
print("\nFirst rows of countries:")
print(countries.head())

# Count missing values per column
print("\nMissing values per column:")
print(restaurants.isnull().sum())

# Distribution of the target candidate column
print("\nAggregate rating statistics:")
print(restaurants["Aggregate rating"].describe())