"""Loads the saved models and turns the values of the Predict page into model inputs (step 17)."""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODEL_PATH = Path(__file__).parent / "models" / "restaurant_models.joblib"

# The file is loaded again when save_model.py has written a newer one
_cache = {"mtime": None, "bundle": None}


def load_bundle():
    """Return the saved models, or None if save_model.py has not been run yet."""
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["bundle"] = joblib.load(MODEL_PATH)
        _cache["mtime"] = mtime
    return _cache["bundle"]


def country_names(bundle):
    """Countries that the models know (they are one-hot columns called country_name_<name>)."""
    prefix = "country_name_"
    return {c[len(prefix):] for c in bundle["columns"] if c.startswith(prefix)}


def cuisine_labels(bundle):
    """Cuisines that the models know (columns called cuisine_<name>), as readable names."""
    prefix = "cuisine_"
    return [c[len(prefix):].replace("_", " ").title() for c in bundle["columns"] if c.startswith(prefix)]


def build_row(bundle, country, cost, median_cost, votes, price_range, booking, delivery, cuisines):
    """Build one row with exactly the features that preprocess.py creates."""
    columns = bundle["columns"]
    row = dict.fromkeys(columns, 0)
    row["price_range"] = price_range
    row["n_cuisines"] = max(1, len(cuisines))
    # Same rule as in preprocess.py: cost divided by the median of its currency
    row["relative_cost"] = cost / median_cost if median_cost > 0 else 1.0
    row["log_votes"] = float(np.log1p(votes))
    row["has_table_booking"] = int(booking)
    row["has_online_delivery"] = int(delivery)
    for label in cuisines:
        row["cuisine_" + label.lower().replace(" ", "_")] = 1
    row["country_name_" + country] = 1
    return pd.DataFrame([row], columns=columns)


def predict(bundle, frame):
    """Return {model name: probability of a high rating} for the one-row frame."""
    return {name: float(model.predict_proba(frame)[0, 1]) for name, model in bundle["models"].items()}
