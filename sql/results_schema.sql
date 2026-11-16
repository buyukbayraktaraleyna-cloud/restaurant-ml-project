-- Tables that store the machine learning results (step 9)

DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS model_metrics;

-- One row per trained model: evaluation metrics measured on the test set
CREATE TABLE model_metrics (
    metric_id       SERIAL PRIMARY KEY,
    model_name      VARCHAR(50) NOT NULL,
    accuracy        NUMERIC(5,4) NOT NULL,
    precision_score NUMERIC(5,4) NOT NULL,
    recall_score    NUMERIC(5,4) NOT NULL,
    f1_score        NUMERIC(5,4) NOT NULL,
    train_seconds   NUMERIC(8,3) NOT NULL,
    test_rows       INTEGER NOT NULL,
    trained_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per (restaurant, model): the prediction made by the model
CREATE TABLE predictions (
    restaurant_id    INTEGER NOT NULL REFERENCES restaurants(restaurant_id),
    model_name       VARCHAR(50) NOT NULL,
    predicted_label  SMALLINT NOT NULL CHECK (predicted_label IN (0, 1)),
    high_probability NUMERIC(5,4) NOT NULL,  -- predicted probability of "high rated"
    actual_label     SMALLINT NOT NULL CHECK (actual_label IN (0, 1)),
    is_test_row      BOOLEAN NOT NULL,       -- TRUE if the row was not used for training
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (restaurant_id, model_name)
);

CREATE INDEX idx_predictions_model ON predictions(model_name);