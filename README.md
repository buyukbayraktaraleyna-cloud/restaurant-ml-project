[README.md](https://github.com/user-attachments/files/35103337/README.md)
# Restaurant Rating Prediction with PostgreSQL and Machine Learning

This is my project for the Database Management Systems course. I used the Zomato restaurants dataset from Kaggle and built a model that predicts whether a restaurant has a high rating (3.5 or more).

The goal was not only to train a model, but to make the database and the model work together. The training data is read straight from PostgreSQL with a SQL query (I never export a CSV for the model), and the predictions and metrics are written back into PostgreSQL and shown from there.

## Architecture

![Architecture diagram](docs/architecture_diagram.png)

Everything runs on one machine. PostgreSQL runs in a Docker container and the Python scripts run locally in a virtual environment. They talk over TCP on `localhost:5432` using SQLAlchemy and psycopg2. There is no API and no cache layer. The editable diagram is in `docs/architecture_diagram.drawio` (it opens in https://app.diagrams.net).

The data flow has five steps:

1. `load_data.py` imports the CSV and Excel files into PostgreSQL.
2. `data_access.py` fetches the training data with a SQL `JOIN`.
3. `preprocess.py` and `train_model.py` clean the data, train the models and test them.
4. `save_results.py` writes the metrics and predictions back to PostgreSQL.
5. `show_results.py` reads the results from the database and shows them.

## Tools

PostgreSQL 16 (Docker image `postgres:16`), Python 3.13, pandas, openpyxl, SQLAlchemy, psycopg2-binary, scikit-learn and matplotlib. The exact package list is in `requirements.txt`.

## Dataset

I used [Zomato Restaurants Data](https://www.kaggle.com/datasets/shrutimehta/zomato-restaurants-data) from Kaggle (the license is on the dataset page). Two files are in the `data/` folder:

- `zomato.csv`: 9,551 restaurants with 21 columns (location, cuisines, cost, price range, online delivery, rating, votes and more)
- `Country-Code.xlsx`: connects the numeric country code to the country name

These files are only used once, to fill the database. After that everything reads from PostgreSQL.

## Project files

```
restaurant-ml-project/
├── data/                    raw dataset files (only for the first import)
├── docs/                    architecture diagram (PNG and draw.io)
├── outputs/                 chart created by show_results.py
├── sql/
│   ├── schema.sql           countries and restaurants tables
│   └── results_schema.sql   model_metrics and predictions tables
├── docker-compose.yml       PostgreSQL container
├── db.py                    database connection settings
├── inspect_data.py          quick look at the raw files (optional)
├── load_data.py             CSV and Excel -> PostgreSQL
├── data_access.py           SQL query that fetches the training data
├── preprocess.py            cleaning and feature engineering
├── train_model.py           training and testing of both models
├── save_results.py          writes metrics and predictions to PostgreSQL
├── show_results.py          reads the results back and shows them
└── requirements.txt
```

## Database design

I used four tables.

`countries` is a small lookup table with `country_code` (primary key) and `country_name`.

`restaurants` has one row per restaurant and 21 columns. `restaurant_id` is the primary key and `country_code` is a foreign key to `countries`, so a restaurant cannot point to a country that does not exist. Yes/No columns are `BOOLEAN`. The rating is `NUMERIC(2,1)` with a check between 0 and 5, and the price range is `SMALLINT` with a check between 1 and 4. I added two indexes, one on `country_code` and one on `aggregate_rating`, because I filter by both.

`model_metrics` stores accuracy, precision, recall, F1, the training time and the number of test rows for each model.

`predictions` has one row for each restaurant and model: the predicted label, the probability of "high rated", the real label and an `is_test_row` flag that tells if the restaurant was kept out of training. The primary key is `(restaurant_id, model_name)`.

Why I designed it this way:

- The country name is in its own table so it is not repeated in thousands of restaurant rows.
- I kept `cuisines` as one comma-separated text column. A fully normalized design would need a cuisine table and a link table, which seemed too much for this project. I split the cuisines later, in the preprocessing step.
- The predictions are stored for all restaurants, not only the test ones, with a flag. This way the metrics can be recomputed in SQL from the stored predictions.

## How to run it

I ran everything on Windows. You need Git, Docker Desktop and Python 3.13 (a recent Python 3 should also work).

**1. Clone the repository**

```
git clone https://github.com/buyukbayraktaraleyna-cloud/restaurant-ml-project.git
cd restaurant-ml-project
```

**2. Create a virtual environment and install the packages**

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux, use `source venv/bin/activate` instead.

**3. Start PostgreSQL**

Open Docker Desktop, wait until it says the engine is running, then run:

```
docker compose up -d
docker ps
```

`docker ps` should show a container called `restaurant_db` with the status `Up`. The settings are in `docker-compose.yml` (database `restaurant_ml`, user `student`, password `student123`, port `5432`). These are only local development credentials.

**4. Create the tables**

```
docker cp sql/schema.sql restaurant_db:/schema.sql
docker exec restaurant_db psql -U student -d restaurant_ml -f /schema.sql
```

**5. Import the dataset**

```
python load_data.py
```

It should print `Loaded 15 countries and 9551 restaurants`.

**6. Train and compare the models (optional)**

```
python train_model.py
```

This only prints the metrics, it does not save anything to the database.

**7. Save the results to PostgreSQL**

```
python save_results.py
```

It should print `Saved 2 metric rows and 14806 predictions to PostgreSQL`. This script also creates the `model_metrics` and `predictions` tables from `sql/results_schema.sql`.

**8. Show the results from the database**

```
python show_results.py
```

It prints the metrics, the confusion matrices, the most confident predictions and the most confident mistakes. It also saves a chart to `outputs/model_comparison.png`.

To check the database directly:

```
docker exec restaurant_db psql -U student -d restaurant_ml -c "SELECT model_name, accuracy, f1_score FROM model_metrics;"
docker exec restaurant_db psql -U student -d restaurant_ml -c "SELECT model_name, ROUND(AVG((predicted_label = actual_label)::int), 3) AS test_accuracy FROM predictions WHERE is_test_row GROUP BY model_name;"
```

The second query calculates the test accuracy again in SQL, using only the stored predictions.

To start over with an empty database, run `docker compose down -v` and `docker compose up -d`, then repeat steps 4 to 8. Step 4 cannot be run again on a database that already has the `predictions` table, because that table depends on `restaurants`.

## From the database to the model

1. **Storage.** `load_data.py` fills the `countries` and `restaurants` tables.
2. **Retrieval.** `data_access.py` runs one SQL query that joins both tables and keeps only restaurants with a rating above 0. That gives 7,403 rows and takes about 0.1 seconds on my computer. A rating of 0 means the restaurant has not been rated yet, so I left out those 2,148 restaurants.
3. **Preprocessing.** The label is 1 if the rating is 3.5 or higher and 0 otherwise (3,480 and 3,923 restaurants, so the two classes are almost balanced). The 9 missing cuisine values became `Unknown`. The cuisines turned into the number of cuisines and 0/1 columns for the 10 most common ones. Costs are in different currencies, so I divided each cost by the median cost of its own currency. The vote count is very skewed, so I used its logarithm. Yes/No columns became 0/1 and the country was one-hot encoded. This gives 33 features. I did not use `rating_color` and `rating_text`, and I removed `aggregate_rating` from the features, because they come directly from the rating and would leak the answer to the model.
4. **Training and testing.** I split the data 80/20 with the same class ratio in both parts (5,922 training rows and 1,481 test rows, `random_state=42`). The numeric columns are standardized with a scaler that is fitted on the training data only.
5. **Write-back.** `save_results.py` stores the metrics and the predictions of both models for all 7,403 restaurants.
6. **Display.** `show_results.py` reads everything from the database tables.

## Results

Metrics on the 1,481 test restaurants:

| Model | Accuracy | Precision | Recall | F1 | Training time |
|---|---|---|---|---|---|
| Logistic Regression | 0.841 | 0.828 | 0.836 | 0.832 | about 0.03 s |
| Random Forest (200 trees) | 0.828 | 0.800 | 0.845 | 0.822 | about 0.2 to 0.3 s |

Confusion matrices (rows are the real class, columns are the predicted class):

| | Logistic Regression | Random Forest |
|---|---|---|
| Real 0 | 664 / 121 | 638 / 147 |
| Real 1 | 114 / 582 | 108 / 588 |

![Model comparison](outputs/model_comparison.png)

The simpler Logistic Regression was a little better than the Random Forest and trained about ten times faster. The most important feature for the Random Forest is the number of votes (about 0.50), followed by the relative cost (0.14), the price range (0.07), the number of cuisines (0.05) and the country India (0.04). Many of the most confident mistakes are restaurants with a real rating close to 3.5, which is the hardest case with this threshold. The training times change a little on every run, but the metrics stay the same because the random seed is fixed.

## Limitations and possible improvements

- The number of votes is the strongest feature, but a new restaurant has no votes yet. The model would work worse for new restaurants.
- I only tested the relational structure (PostgreSQL tables). I did not compare it with a document structure such as MongoDB.
- The 3.5 threshold was my choice. Other thresholds, or a regression model that predicts the rating itself, could be tried.
- The models could be improved with more features and with cross-validation.
- This is a single-machine setup. For much more data, the database could move to a managed or distributed service and the model could be offered through an API.
