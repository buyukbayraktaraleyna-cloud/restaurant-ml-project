"""Train both models on ALL rated restaurants and save them to a file (step 17).

The web panel loads this file to answer the "what if?" questions on the Predict page.
The data is read from PostgreSQL, the same way as in train_model.py.

Run it once:   python save_model.py
The file is written to models/restaurant_models.joblib
"""
from pathlib import Path

import joblib

from data_access import load_restaurants_from_db
from preprocess import preprocess
from train_model import build_models

MODEL_PATH = Path(__file__).parent / "models" / "restaurant_models.joblib"


def main():
    raw = load_restaurants_from_db()
    X, y, _ids = preprocess(raw)
    print(f"Loaded {len(X)} rows and {X.shape[1]} features from PostgreSQL")

    models = build_models()
    for name, model in models.items():
        # Unlike train_model.py, no rows are kept out here: this file is only
        # used to predict new restaurants, the test results come from train_model.py
        model.fit(X, y)
        print(f"Trained {name}")

    MODEL_PATH.parent.mkdir(exist_ok=True)
    # The column list is saved too, so the panel builds the inputs in the same order
    joblib.dump(
        {"columns": list(X.columns), "models": models, "trained_rows": len(X)},
        MODEL_PATH,
        compress=3,  # the trees compress well, the file gets much smaller
    )
    size_mb = MODEL_PATH.stat().st_size / 1024 / 1024
    print(f"Saved {len(models)} models to {MODEL_PATH.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
