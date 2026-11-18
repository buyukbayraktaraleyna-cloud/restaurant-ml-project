"""Show the model results by reading them back from PostgreSQL (step 10)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw into a file, no window is opened
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import text

from db import get_engine

MODEL = "Logistic Regression"  # model used for the example lists below


def query(conn, sql, **params):
    """Run a SQL query and return the result as a DataFrame."""
    return pd.read_sql(text(sql), conn, params=params)


def main():
    engine = get_engine()
    with engine.connect() as conn:
        # 1. Evaluation metrics saved by save_results.py
        metrics = query(
            conn,
            """
            SELECT model_name, accuracy, precision_score, recall_score,
                   f1_score, train_seconds, test_rows
            FROM model_metrics
            ORDER BY f1_score DESC
            """,
        )
        print("Model metrics (read from the model_metrics table):")
        print(metrics.round(3).to_string(index=False))

        # 2. Confusion matrix of each model, computed with SQL on the test rows
        confusion = query(
            conn,
            """
            SELECT model_name, actual_label, predicted_label, COUNT(*) AS n
            FROM predictions
            WHERE is_test_row
            GROUP BY model_name, actual_label, predicted_label
            """,
        )
        for model_name, part in confusion.groupby("model_name"):
            matrix = part.pivot_table(
                index="actual_label",
                columns="predicted_label",
                values="n",
                fill_value=0,
            )
            print(f"\nConfusion matrix - {model_name} (rows = actual, columns = predicted):")
            print(matrix)

        # 3. Restaurants the model is most sure are highly rated (test rows only)
        top = query(
            conn,
            """
            SELECT r.restaurant_name, r.city, r.aggregate_rating,
                   p.high_probability
            FROM predictions p
            JOIN restaurants r ON r.restaurant_id = p.restaurant_id
            WHERE p.is_test_row AND p.model_name = :model
            ORDER BY p.high_probability DESC
            LIMIT 10
            """,
            model=MODEL,
        )
        print(f"\nTop 10 most confident 'high rated' predictions ({MODEL}):")
        print(top.round(3).to_string(index=False))

        # 4. The most confident mistakes of the model (useful for error analysis)
        mistakes = query(
            conn,
            """
            SELECT r.restaurant_name, r.city, r.aggregate_rating,
                   p.predicted_label, p.high_probability
            FROM predictions p
            JOIN restaurants r ON r.restaurant_id = p.restaurant_id
            WHERE p.is_test_row
              AND p.model_name = :model
              AND p.predicted_label <> p.actual_label
            ORDER BY ABS(p.high_probability - 0.5) DESC
            LIMIT 10
            """,
            model=MODEL,
        )
        print(f"\nTop 10 most confident mistakes ({MODEL}):")
        print(mistakes.round(3).to_string(index=False))

    # 5. Bar chart that compares the models, saved as a PNG file
    Path("outputs").mkdir(exist_ok=True)
    metric_columns = ["accuracy", "precision_score", "recall_score", "f1_score"]
    chart_data = metrics.set_index("model_name")[metric_columns].astype(float).T
    ax = chart_data.plot(kind="bar", figsize=(8, 5), ylim=(0, 1))
    ax.set_title("Model comparison on the test set")
    ax.set_ylabel("Score")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig("outputs/model_comparison.png", dpi=150)
    print("\nChart saved to outputs/model_comparison.png")


if __name__ == "__main__":
    main()