"""Load the Zomato CSV and the country Excel file into PostgreSQL (step 5)."""

import pandas as pd
from sqlalchemy import text

from db import get_engine

# 1. Read the raw files (the CSV uses latin-1 encoding)
restaurants = pd.read_csv("data/zomato.csv", encoding="latin-1")
countries = pd.read_excel("data/Country-Code.xlsx")

# 2. Rename columns so they match the database schema
countries = countries.rename(
    columns={"Country Code": "country_code", "Country": "country_name"}
)
restaurants = restaurants.rename(
    columns={
        "Restaurant ID": "restaurant_id",
        "Restaurant Name": "restaurant_name",
        "Country Code": "country_code",
        "City": "city",
        "Address": "address",
        "Locality": "locality",
        "Locality Verbose": "locality_verbose",
        "Longitude": "longitude",
        "Latitude": "latitude",
        "Cuisines": "cuisines",
        "Average Cost for two": "average_cost_for_two",
        "Currency": "currency",
        "Has Table booking": "has_table_booking",
        "Has Online delivery": "has_online_delivery",
        "Is delivering now": "is_delivering_now",
        "Switch to order menu": "switch_to_order_menu",
        "Price range": "price_range",
        "Aggregate rating": "aggregate_rating",
        "Rating color": "rating_color",
        "Rating text": "rating_text",
        "Votes": "votes",
    }
)

# 3. Convert the Yes/No text columns to real booleans
bool_columns = [
    "has_table_booking",
    "has_online_delivery",
    "is_delivering_now",
    "switch_to_order_menu",
]
for col in bool_columns:
    restaurants[col] = restaurants[col].map({"Yes": True, "No": False})

# 4. Remove duplicated restaurant IDs (the primary key must be unique)
rows_before = len(restaurants)
restaurants = restaurants.drop_duplicates(subset="restaurant_id")
print(f"Removed {rows_before - len(restaurants)} duplicated restaurant IDs")

# 5. Every country code used by a restaurant must exist in the countries table
missing_codes = set(restaurants["country_code"]) - set(countries["country_code"])
if missing_codes:
    raise SystemExit(f"Country codes missing from the Excel file: {missing_codes}")

# 6. Write both tables inside one transaction (all or nothing)
engine = get_engine()
with engine.begin() as conn:
    # Empty both tables first so the script can be re-run safely
    conn.execute(text("TRUNCATE TABLE restaurants, countries"))
    countries.to_sql("countries", conn, if_exists="append", index=False)
    restaurants.to_sql(
        "restaurants",
        conn,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    # Read the row counts back from the database to confirm the load
    n_countries = conn.execute(text("SELECT COUNT(*) FROM countries")).scalar()
    n_restaurants = conn.execute(text("SELECT COUNT(*) FROM restaurants")).scalar()

print(f"Loaded {n_countries} countries and {n_restaurants} restaurants")