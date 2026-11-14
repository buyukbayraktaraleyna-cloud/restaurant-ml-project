"""Cleaning and feature engineering for the restaurant data (step 7)."""

import numpy as np
import pandas as pd

from data_access import load_restaurants_from_db

# Restaurants rated at or above this value are labelled "high rated" (1)
RATING_THRESHOLD = 3.5
# Number of most frequent cuisines that become 0/1 columns
TOP_CUISINES = 10


def preprocess(df):
    """Clean the raw DataFrame and return (features, target, restaurant ids)."""
    df = df.copy()

    # 1. Target: 1 if the restaurant is highly rated, otherwise 0
    y = (df["aggregate_rating"] >= RATING_THRESHOLD).astype(int)

    # 2. Keep the restaurant ids so predictions can be saved back to the database
    ids = df["restaurant_id"]

    # 3. Fill the few missing cuisine values with a placeholder
    df["cuisines"] = df["cuisines"].fillna("Unknown")

    # 4. Cuisine features: number of cuisines and 0/1 flags for the most common ones
    cuisine_lists = df["cuisines"].str.split(",").apply(
        lambda items: [c.strip() for c in items]
    )
    df["n_cuisines"] = cuisine_lists.apply(len)
    top_cuisines = (
        pd.Series([c for items in cuisine_lists for c in items])
        .value_counts()
        .head(TOP_CUISINES)
        .index
    )
    for cuisine in top_cuisines:
        column_name = "cuisine_" + cuisine.lower().replace(" ", "_")
        df[column_name] = cuisine_lists.apply(lambda items: int(cuisine in items))

    # 5. Costs use different currencies, so compare each cost with the median
    #    cost of its own currency (a median of 0 is treated as unknown -> ratio 1)
    median_cost = df.groupby("currency")["average_cost_for_two"].transform("median")
    df["relative_cost"] = (
        df["average_cost_for_two"] / median_cost.replace(0, np.nan)
    ).fillna(1.0)

    # 6. Votes are very skewed, so a log transform reduces the effect of outliers
    df["log_votes"] = np.log1p(df["votes"])

    # 7. Convert the True/False columns to 1/0
    bool_columns = [
        "has_table_booking",
        "has_online_delivery",
        "is_delivering_now",
        "switch_to_order_menu",
    ]
    df[bool_columns] = df[bool_columns].astype(int)

    # 8. One-hot encode the country
    df = pd.get_dummies(df, columns=["country_name"], dtype=int)

    # 9. Drop the columns that must not be used as features
    drop_columns = [
        "restaurant_id",
        "restaurant_name",
        "city",          # too many different values
        "cuisines",      # replaced by the cuisine features
        "currency",      # replaced by relative_cost
        "average_cost_for_two",
        "votes",         # replaced by log_votes
        "aggregate_rating",  # this is what the target is built from (data leakage)
    ]
    features = df.drop(columns=drop_columns)

    return features, y, ids


if __name__ == "__main__":
    raw = load_restaurants_from_db()
    X, y, ids = preprocess(raw)

    print("Feature matrix shape:", X.shape)
    print("\nFeature columns:")
    print(list(X.columns))
    print("\nClass balance (0 = below 3.5, 1 = 3.5 or higher):")
    print(y.value_counts())
    print("\nMissing values in features:", int(X.isnull().sum().sum()))