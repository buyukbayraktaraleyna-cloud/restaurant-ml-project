"""Save the model metrics and predictions back to PostgreSQL (step 9)."""

import time
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from db import get_engine
from train_model import build_models, split_data


def create_result_tables(engine):
    """Create the result tables by running sql/results_schema.sql."""
    sql = Path("sql/results_schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def main():
    # Data comes straight from PostgreSQL (see data_access.py)
    X_train, X_test, y_train, y_test, ids_train, ids_test = split_data()
    engine = get_engine()
    create_result_tables(engine)

    metric_rows = []
    prediction_frames = []

    for name, model in build_models().items():
        # Train the model and measure the training time
        start = time.perf_counter()
        model.fit(X_train, y_train)
        train_seconds = time.perf_counter() - start

        # Metrics are measured on the test rows only
        y_pred_test = model.predict(X_test)
        metric_rows.append(
            {
                "model_name": name,
                "accuracy": accuracy_score(y_test, y_pred_test),
                "precision_score": precision_score(y_test, y_pred_test),
                "recall_score": recall_score(y_test, y_pred_test),
                "f1_score": f1_score(y_test, y_pred_test),
                "train_seconds": train_seconds,
                "test_rows": len(y_test),
            }
        )

        # Predictions are stored for every rated restaurant (train and test rows)
        parts = [
            (X_train, y_train, ids_train, False),
            (X_test, y_test, ids_test, True),
        ]
        for X_part, y_part, ids_part, is_test in parts:
            prediction_frames.append(
                pd.DataFrame(
                    {
                        "restaurant_id": ids_part.values,
                        "model_name": name,
                        "predicted_label": model.predict(X_part),
                        "high_probability": model.predict_proba(X_part)[:, 1],
                        "actual_label": y_part.values,
                        "is_test_row": is_test,
                    }
                )
            )

    metrics = pd.DataFrame(metric_rows)
    predictions = pd.concat(prediction_frames, ignore_index=True)

    # Write both result tables in one transaction (all or nothing)
    with engine.begin() as conn:
        metrics.to_sql("model_metrics", conn, if_exists="append", index=False)
        predictions.to_sql(
            "predictions",
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500,
        )

    print(f"Saved {len(metrics)} metric rows and {len(predictions)} predictions to PostgreSQL")


if __name__ == "__main__":
    main()