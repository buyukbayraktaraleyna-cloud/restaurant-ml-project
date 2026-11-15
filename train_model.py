"""Train and test the classification models (step 8)."""

import time

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data_access import load_restaurants_from_db
from preprocess import preprocess

RANDOM_STATE = 42  # fixed seed so the split is the same on every run
TEST_SIZE = 0.2    # 20% of the rows are kept for testing

# Numeric columns that are normalised (mean 0, std 1) for Logistic Regression
NUMERIC_COLUMNS = ["price_range", "n_cuisines", "relative_cost", "log_votes"]


def split_data():
    """Fetch data from PostgreSQL, preprocess it and split it into train/test."""
    raw = load_restaurants_from_db()
    X, y, ids = preprocess(raw)
    # stratify=y keeps the same class ratio in the train and test sets
    return train_test_split(
        X, y, ids, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )


def build_models():
    """Return the models to compare, keyed by name."""
    # Scale only the numeric columns; the 0/1 columns are passed through unchanged
    scaler = ColumnTransformer(
        [("scale", StandardScaler(), NUMERIC_COLUMNS)], remainder="passthrough"
    )
    return {
        "Logistic Regression": Pipeline(
            [("prep", scaler), ("model", LogisticRegression(max_iter=1000))]
        ),
        # Trees do not need scaling
        "Random Forest": RandomForestClassifier(
            n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1
        ),
    }


if __name__ == "__main__":
    X_train, X_test, y_train, y_test, ids_train, ids_test = split_data()
    print(f"Training rows: {len(X_train)}, test rows: {len(X_test)}")

    models = build_models()
    results = []

    for name, model in models.items():
        # Train the model and measure the training time
        start = time.perf_counter()
        model.fit(X_train, y_train)
        train_seconds = time.perf_counter() - start

        # Predict on the unseen test rows and compute the metrics
        y_pred = model.predict(X_test)
        results.append(
            {
                "model": name,
                "accuracy": accuracy_score(y_test, y_pred),
                "precision": precision_score(y_test, y_pred),
                "recall": recall_score(y_test, y_pred),
                "f1": f1_score(y_test, y_pred),
                "train_seconds": train_seconds,
            }
        )
        print(f"\n{name} - confusion matrix (rows = actual, columns = predicted):")
        print(confusion_matrix(y_test, y_pred))

    print("\nModel comparison:")
    print(pd.DataFrame(results).round(3).to_string(index=False))

    # Show which features the Random Forest found most useful
    forest = models["Random Forest"]
    importances = pd.Series(forest.feature_importances_, index=X_train.columns)
    print("\nTop 8 features (Random Forest):")
    print(importances.sort_values(ascending=False).head(8).round(3))