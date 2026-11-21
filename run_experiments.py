"""
Extra experiments that make the results more reliable.

1. 5-fold cross-validation: are the results stable, or just lucky?
2. Different rating thresholds: what happens if "high rated" means 3.0 or 4.0?
3. No vote count: how good is the model for a NEW restaurant that has no votes?

The data is read from PostgreSQL, the same way as in train_model.py.
Nothing is written to the database.
"""
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

import train_model
from data_access import load_restaurants_from_db
from preprocess import preprocess

SEED = train_model.RANDOM_STATE


def fit_and_score(X, y):
    """Split 80/20 (same as train_model.py), train both models, return metrics."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=train_model.TEST_SIZE, stratify=y, random_state=SEED
    )
    rows = []
    for name, model in train_model.build_models().items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        rows.append({
            "model": name,
            "accuracy": accuracy_score(y_test, pred),
            "f1": f1_score(y_test, pred),
        })
    return rows


def main():
    raw = load_restaurants_from_db()
    X, y, ids = preprocess(raw)
    print(f"Loaded {len(X)} rows and {X.shape[1]} features from PostgreSQL\n")

    # ---- 1. Cross-validation -------------------------------------------------
    print("1) 5-fold cross-validation (mean +/- standard deviation over 5 folds)")
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    for name, model in train_model.build_models().items():
        scores = cross_validate(model, X, y, cv=folds, scoring=["accuracy", "f1"])
        acc, f1 = scores["test_accuracy"], scores["test_f1"]
        print(f"   {name:<22} accuracy {acc.mean():.3f} +/- {acc.std():.3f}"
              f"   F1 {f1.mean():.3f} +/- {f1.std():.3f}")

    # ---- 2. Rating threshold -------------------------------------------------
    print("\n2) Different thresholds for 'high rated' (same features, 80/20 split)")
    print(f"   {'Threshold':<10}{'High rated':>11}{'Model':>24}{'Accuracy':>10}{'F1':>8}")
    for threshold in (3.0, 3.5, 4.0):
        y_t = (raw["aggregate_rating"] >= threshold).astype(int)
        share = y_t.mean()
        for row in fit_and_score(X, y_t):
            print(f"   {threshold:<10}{share:>10.0%}{row['model']:>24}"
                  f"{row['accuracy']:>10.3f}{row['f1']:>8.3f}")

    # ---- 3. Without the vote count ------------------------------------------
    print("\n3) Without the vote count (like a brand-new restaurant)")
    # log_votes is removed from the features and from the scaled columns
    original_numeric = train_model.NUMERIC_COLUMNS
    train_model.NUMERIC_COLUMNS = [c for c in original_numeric if c != "log_votes"]
    try:
        with_votes = fit_and_score(X, y)
        without_votes = fit_and_score(X.drop(columns=["log_votes"]), y)
    finally:
        train_model.NUMERIC_COLUMNS = original_numeric
    print(f"   {'Model':<22}{'Accuracy with':>15}{'Accuracy without':>18}{'F1 with':>10}{'F1 without':>12}")
    for a, b in zip(with_votes, without_votes):
        print(f"   {a['model']:<22}{a['accuracy']:>15.3f}{b['accuracy']:>18.3f}"
              f"{a['f1']:>10.3f}{b['f1']:>12.3f}")


if __name__ == "__main__":
    main()
