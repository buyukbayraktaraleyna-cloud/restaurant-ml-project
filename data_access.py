"""Fetch the model training data directly from PostgreSQL (step 6)."""

import time

import pandas as pd
from sqlalchemy import text

from db import get_engine

# SQL query used by the model: joins both tables and keeps only rated restaurants.
# rating_color and rating_text are NOT selected because they are derived from the
# rating itself (data leakage).
QUERY = """
SELECT
    r.restaurant_id,
    r.restaurant_name,
    c.country_name,
    r.city,
    r.cuisines,
    r.average_cost_for_two,
    r.currency,
    r.has_table_booking,
    r.has_online_delivery,
    r.is_delivering_now,
    r.switch_to_order_menu,
    r.price_range,
    r.votes,
    r.aggregate_rating
FROM restaurants r
JOIN countries c ON r.country_code = c.country_code
WHERE r.aggregate_rating > 0   -- 0 means "not rated yet", so we exclude it
"""


def load_restaurants_from_db():
    """Run the SQL query and return the result as a pandas DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(QUERY), conn)


if __name__ == "__main__":
    # Measure how long the query takes (useful for the report)
    start = time.perf_counter()
    df = load_restaurants_from_db()
    elapsed = time.perf_counter() - start

    print(f"Fetched {len(df)} rows and {df.shape[1]} columns in {elapsed:.3f} seconds")
    print("\nColumns and data types:")
    print(df.dtypes)
    print("\nFirst 3 rows:")
    print(df.head(3).T)