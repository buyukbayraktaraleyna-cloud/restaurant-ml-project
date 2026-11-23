"""Web panel that shows the data and the model results stored in PostgreSQL (step 13-16).

Run it with:   python app.py
Then open:     http://127.0.0.1:5000

Pages:
    /                       model metrics and confusion matrices
    /stats                  statistics computed with SQL (ratings, countries, cuisines)
    /restaurants            browse and filter all restaurants
    /restaurant/<id>        details of one restaurant and the prediction of each model
    /search                 search by name and see the predictions directly
    /mistakes               most confident mistakes of a model
    /export/predictions.csv download all stored predictions
    /predict                "what if?" form: the saved models predict a restaurant you describe
    /lang/<code>            choose the language (en, tr, de, ar, zh)

JSON API (step 17):
    GET  /api/metrics               metrics of the models
    GET  /api/restaurants           restaurants (?limit=&offset=&country=&q=)
    GET  /api/restaurants/<id>      one restaurant with its predictions
    POST /api/predict               prediction for a restaurant described in JSON

The HTML pages are in the templates folder, the CSS and JavaScript are in the static folder.
The panel only reads from the database, it never changes any data.
"""

import csv
import io
import math
from decimal import Decimal
from math import ceil
from urllib.parse import urlencode

from flask import Flask, Response, abort, jsonify, redirect, render_template, request
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

import predictor
from db import get_engine
from translations import DEFAULT_LANGUAGE, LANGUAGES, RTL_LANGUAGES, translate

app = Flask(__name__)
engine = get_engine()

PAGE_SIZE = 20  # restaurants per page in the browse page


def current_language():
    """Language chosen by the visitor (stored in a cookie), English if nothing was chosen."""
    code = request.cookies.get("lang", DEFAULT_LANGUAGE)
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def t(key, **params):
    """Return the text with this key in the current language."""
    return translate(key, current_language(), **params)


# t() can be used in every template and in every macro
app.jinja_env.globals["t"] = t


@app.context_processor
def inject_template_helpers():
    """Variables that every template can use."""
    language = current_language()
    return {
        # the small template macros (rating badge, bar) are available as ui
        "ui": app.jinja_env.get_template("macros.html").module,
        "lang": language,
        "languages": LANGUAGES,
        "rtl": language in RTL_LANGUAGES,
        "direction": "rtl" if language in RTL_LANGUAGES else "ltr",
        # the address of the current page, used by the language links to come back here
        "current_url": request.full_path.rstrip("?"),
    }


def fetch_all(sql, **params):
    """Run a read-only SQL query and return the rows as a list of dictionaries."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row) for row in result.mappings()]


def like_pattern(user_text):
    """Turn the text typed by the user into a safe ILIKE pattern."""
    escaped = user_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def add_percent(rows, key, field="pct"):
    """Add a field with the value of `key` as a percentage of the largest value."""
    top = max((float(row[key]) for row in rows), default=0) or 1
    for row in rows:
        row[field] = float(row[key]) / top * 100


def add_rating_percent(rows, key="avg_rating", field="avg_pct"):
    """Add a field with an average rating (0 to 5) as a percentage."""
    for row in rows:
        value = row[key]
        row[field] = float(value) / 5 * 100 if value is not None else 0


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Metrics and confusion matrices of all trained models."""
    metrics = fetch_all(
        """
        SELECT model_name, accuracy, precision_score, recall_score,
               f1_score, train_seconds, test_rows
        FROM model_metrics
        ORDER BY f1_score DESC
        """
    )

    # Confusion matrix of each model, computed in SQL on the test rows only
    confusion = fetch_all(
        """
        SELECT model_name, actual_label, predicted_label, COUNT(*) AS n
        FROM predictions
        WHERE is_test_row
        GROUP BY model_name, actual_label, predicted_label
        """
    )
    matrices = {}
    for row in confusion:
        matrix = matrices.setdefault(row["model_name"], [[0, 0], [0, 0]])
        matrix[row["actual_label"]][row["predicted_label"]] = row["n"]
    matrices = dict(sorted(matrices.items()))

    counts = fetch_all(
        """
        SELECT
            (SELECT COUNT(*) FROM restaurants) AS n_restaurants,
            (SELECT COUNT(*) FROM restaurants WHERE aggregate_rating > 0) AS n_rated,
            (SELECT COUNT(*) FROM predictions) AS n_predictions
        """
    )[0]

    return render_template("index.html", active="home", metrics=metrics, matrices=matrices, **counts)


@app.route("/stats")
def stats():
    """Statistics about the restaurants, calculated with SQL."""
    # Rating distribution: restaurants grouped by the integer part of the rating
    buckets = fetch_all(
        """
        SELECT FLOOR(aggregate_rating)::int AS bucket, COUNT(*) AS n
        FROM restaurants
        WHERE aggregate_rating > 0
        GROUP BY FLOOR(aggregate_rating)::int
        ORDER BY bucket
        """
    )
    for row in buckets:
        row["label"] = f"{row['bucket']}.0 - {row['bucket']}.9"
    add_percent(buckets, "n")

    unrated = fetch_all("SELECT COUNT(*) AS n FROM restaurants WHERE aggregate_rating = 0")[0]["n"]

    prices = fetch_all(
        """
        SELECT price_range, COUNT(*) AS n,
               ROUND(AVG(NULLIF(aggregate_rating, 0)), 2) AS avg_rating
        FROM restaurants
        GROUP BY price_range
        ORDER BY price_range
        """
    )
    add_rating_percent(prices)

    delivery = fetch_all(
        """
        SELECT has_online_delivery, COUNT(*) AS n,
               ROUND(AVG(NULLIF(aggregate_rating, 0)), 2) AS avg_rating
        FROM restaurants
        GROUP BY has_online_delivery
        ORDER BY has_online_delivery DESC
        """
    )
    add_rating_percent(delivery)

    # The cuisines are stored as one comma-separated text, so we split them in SQL
    cuisines = fetch_all(
        """
        SELECT TRIM(cuisine) AS cuisine, COUNT(*) AS n,
               ROUND(AVG(NULLIF(r.aggregate_rating, 0)), 2) AS avg_rating
        FROM restaurants r, regexp_split_to_table(r.cuisines, ',') AS cuisine
        GROUP BY TRIM(cuisine)
        ORDER BY n DESC, TRIM(cuisine)
        LIMIT 10
        """
    )
    add_percent(cuisines, "n")

    countries = fetch_all(
        """
        SELECT c.country_name, COUNT(*) AS n,
               ROUND(AVG(NULLIF(r.aggregate_rating, 0)), 2) AS avg_rating
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        GROUP BY c.country_name
        ORDER BY n DESC, c.country_name
        """
    )
    add_percent(countries, "n")
    add_rating_percent(countries)

    return render_template(
        "stats.html",
        active="stats",
        buckets=buckets,
        unrated=unrated,
        prices=prices,
        delivery=delivery,
        cuisines=cuisines,
        countries=countries,
    )


@app.route("/restaurants")
def browse():
    """List restaurants with filters and pages."""
    f = {
        "q": request.args.get("q", "").strip(),
        "country": request.args.get("country", "").strip(),
        "price": request.args.get("price", "").strip(),
        "delivery": request.args.get("delivery", "").strip(),
    }

    # Build the WHERE part from fixed pieces, the values are bind parameters
    conditions = []
    params = {}
    if f["q"]:
        conditions.append("r.restaurant_name ILIKE :pattern")
        params["pattern"] = like_pattern(f["q"])
    if f["country"].isdigit():
        conditions.append("r.country_code = :country")
        params["country"] = int(f["country"])
    if f["price"] in ("1", "2", "3", "4"):
        conditions.append("r.price_range = :price")
        params["price"] = int(f["price"])
    if f["delivery"] == "1":
        conditions.append("r.has_online_delivery")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = fetch_all(f"SELECT COUNT(*) AS n FROM restaurants r {where}", **params)[0]["n"]
    total_pages = max(1, ceil(total / PAGE_SIZE))
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = min(max(page, 1), total_pages)

    rows = fetch_all(
        f"""
        SELECT r.restaurant_id, r.restaurant_name, r.city, c.country_name,
               r.price_range, r.aggregate_rating, r.votes
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        {where}
        ORDER BY r.votes DESC, r.restaurant_id
        LIMIT :limit OFFSET :offset
        """,
        limit=PAGE_SIZE,
        offset=(page - 1) * PAGE_SIZE,
        **params,
    )

    countries = fetch_all("SELECT country_code, country_name FROM countries ORDER BY country_name")

    def page_url(number):
        query = {key: value for key, value in f.items() if value}
        query["page"] = number
        return "/restaurants?" + urlencode(query)

    return render_template(
        "browse.html",
        active="browse",
        f=f,
        rows=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        countries=countries,
        prev_url=page_url(page - 1) if page > 1 else None,
        next_url=page_url(page + 1) if page < total_pages else None,
    )


@app.route("/restaurant/<int:restaurant_id>")
def restaurant_detail(restaurant_id):
    """All details of one restaurant and the prediction of each model."""
    rows = fetch_all(
        """
        SELECT r.restaurant_id, r.restaurant_name, r.city, r.address, r.locality,
               r.cuisines, r.average_cost_for_two, r.currency, r.price_range,
               r.has_table_booking, r.has_online_delivery, r.votes,
               r.aggregate_rating, c.country_name
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        WHERE r.restaurant_id = :rid
        """,
        rid=restaurant_id,
    )
    if not rows:
        abort(404)

    predictions = fetch_all(
        """
        SELECT model_name, predicted_label, high_probability, actual_label, is_test_row
        FROM predictions
        WHERE restaurant_id = :rid
        ORDER BY model_name
        """,
        rid=restaurant_id,
    )
    return render_template("detail.html", active="browse", r=rows[0], predictions=predictions)


@app.route("/search")
def search():
    """Find restaurants by name and show the prediction of each model."""
    q = request.args.get("q", "").strip()
    results = []

    if q:
        # The search text is passed as a bind parameter (protects against SQL injection)
        results = fetch_all(
            """
            SELECT r.restaurant_id, r.restaurant_name, r.city, c.country_name,
                   r.aggregate_rating, r.votes
            FROM restaurants r
            JOIN countries c ON c.country_code = r.country_code
            WHERE r.restaurant_name ILIKE :pattern
            ORDER BY r.votes DESC
            LIMIT 10
            """,
            pattern=like_pattern(q),
        )
        for restaurant in results:
            restaurant["predictions"] = fetch_all(
                """
                SELECT model_name, predicted_label, high_probability,
                       actual_label, is_test_row
                FROM predictions
                WHERE restaurant_id = :rid
                ORDER BY model_name
                """,
                rid=restaurant["restaurant_id"],
            )

    return render_template("search.html", active="search", q=q, results=results)


@app.route("/mistakes")
def mistakes():
    """Test restaurants that the chosen model got wrong with high confidence."""
    models = [
        row["model_name"]
        for row in fetch_all("SELECT model_name FROM model_metrics ORDER BY model_name")
    ]
    model = request.args.get("model", "")
    if models and model not in models:
        model = models[0]

    rows = []
    if models:
        rows = fetch_all(
            """
            SELECT r.restaurant_id, r.restaurant_name, r.city, r.aggregate_rating,
                   p.predicted_label, p.high_probability
            FROM predictions p
            JOIN restaurants r ON r.restaurant_id = p.restaurant_id
            WHERE p.is_test_row
              AND p.model_name = :model
              AND p.predicted_label <> p.actual_label
            ORDER BY ABS(p.high_probability - 0.5) DESC
            LIMIT 20
            """,
            model=model,
        )

    return render_template("mistakes.html", active="mistakes", models=models, model=model, rows=rows)


# ---------------------------------------------------------------------------
# "What if?" prediction (step 17): the form and the JSON API use the same code
# ---------------------------------------------------------------------------


class InputError(ValueError):
    """The values of the form or of the JSON request are not valid."""


def country_cost_info():
    """Currency and typical cost for two of every country (from the rated restaurants).

    The models use the cost relative to the median cost of the currency, so the
    median is needed to turn the cost typed by the visitor into the model feature.
    """
    medians = {
        row["currency"]: row["median_cost"]
        for row in fetch_all(
            """
            SELECT currency,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY average_cost_for_two) AS median_cost
            FROM restaurants
            WHERE aggregate_rating > 0
            GROUP BY currency
            """
        )
    }
    rows = fetch_all(
        """
        SELECT c.country_name, r.currency, COUNT(*) AS n
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        WHERE r.aggregate_rating > 0
        GROUP BY c.country_name, r.currency
        ORDER BY c.country_name, n DESC
        """
    )
    info = {}
    for row in rows:
        if row["country_name"] not in info:  # the most common currency comes first
            median = float(medians.get(row["currency"]) or 0)
            info[row["country_name"]] = {"currency": row["currency"], "median": round(median, 2)}
    return info


def as_bool(value):
    """True for the usual 'yes' values (checkbox 'on', '1', 'true', JSON true)."""
    return str(value).strip().lower() in ("1", "on", "true", "yes")


def parse_prediction_inputs(data, bundle, info):
    """Check the values and return them in a clean form. Raises InputError if something is wrong."""
    country = str(data.get("country", "")).strip()
    if country not in info or country not in predictor.country_names(bundle):
        raise InputError("country")
    try:
        cost = float(data.get("cost"))
        votes = int(float(data.get("votes")))
        price_range = int(float(data.get("price_range")))
    except (TypeError, ValueError):
        raise InputError("number")
    if not math.isfinite(cost) or not 0 <= cost <= 10_000_000:
        raise InputError("cost")
    if not 0 <= votes <= 10_000_000:
        raise InputError("votes")
    if price_range not in (1, 2, 3, 4):
        raise InputError("price_range")

    known = predictor.cuisine_labels(bundle)
    cuisines = data.get("cuisines") or []
    if not isinstance(cuisines, list) or any(c not in known for c in cuisines):
        raise InputError("cuisines")

    return {
        "country": country,
        "cost": cost,
        "votes": votes,
        "price_range": price_range,
        "table_booking": as_bool(data.get("table_booking", False)),
        "online_delivery": as_bool(data.get("online_delivery", False)),
        "cuisines": cuisines,
    }


def run_prediction(values, bundle, info):
    """Predict twice: with the votes given, and as a brand-new restaurant with 0 votes."""
    country_info = info[values["country"]]
    probabilities = {}
    for key, votes in (("with_votes", values["votes"]), ("no_votes", 0)):
        frame = predictor.build_row(
            bundle, values["country"], values["cost"], country_info["median"], votes,
            values["price_range"], values["table_booking"], values["online_delivery"],
            values["cuisines"],
        )
        for model_name, probability in predictor.predict(bundle, frame).items():
            probabilities.setdefault(model_name, {})[key] = probability
    median = country_info["median"]
    return {
        "currency": country_info["currency"],
        "relative_cost": round(values["cost"] / median, 2) if median > 0 else 1.0,
        "probabilities": dict(sorted(probabilities.items())),
    }


@app.route("/predict")
def predict_page():
    """Form where the visitor describes a restaurant and the saved models predict the rating class."""
    bundle = predictor.load_bundle()
    if bundle is None:
        return render_template("predict.html", active="predict", no_model=True)

    info = country_cost_info()
    known_countries = predictor.country_names(bundle)
    country_info = {name: data for name, data in info.items() if name in known_countries}
    f = {
        "country": request.args.get("country", ""),
        "cost": request.args.get("cost", ""),
        "votes": request.args.get("votes", "50"),
        "price_range": request.args.get("price_range", "2"),
        "table_booking": as_bool(request.args.get("table_booking", False)),
        "online_delivery": as_bool(request.args.get("online_delivery", False)),
        "cuisines": request.args.getlist("cuisines"),
    }

    result, error = None, False
    if request.args.get("country"):  # the form was sent
        try:
            values = parse_prediction_inputs(f, bundle, info)
            result = run_prediction(values, bundle, info)
        except InputError:
            error = True

    return render_template(
        "predict.html",
        active="predict",
        no_model=False,
        f=f,
        countries=sorted(country_info),
        country_info=country_info,
        cuisines=predictor.cuisine_labels(bundle),
        trained_rows=bundle["trained_rows"],
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# JSON API (step 17)
# ---------------------------------------------------------------------------


def jsonable(value):
    """Decimal numbers (from PostgreSQL NUMERIC columns) become normal floats for JSON."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def api_error(message, status):
    """JSON error answer for the API."""
    return jsonify({"error": message}), status


@app.route("/api/metrics")
def api_metrics():
    """Metrics of all models."""
    rows = fetch_all(
        """
        SELECT model_name, accuracy, precision_score, recall_score, f1_score,
               train_seconds, test_rows
        FROM model_metrics
        ORDER BY model_name
        """
    )
    return jsonify(jsonable(rows))


@app.route("/api/restaurants")
def api_restaurants():
    """Restaurants as JSON. Optional: ?limit=20&offset=0&country=<code>&q=<text>."""
    try:
        limit = min(max(int(request.args.get("limit", "20")), 1), 100)
        offset = max(int(request.args.get("offset", "0")), 0)
    except ValueError:
        return api_error("limit and offset must be whole numbers", 400)

    conditions, params = [], {}
    country = request.args.get("country", "").strip()
    if country:
        if not country.isdigit():
            return api_error("country must be a country code (a number)", 400)
        conditions.append("r.country_code = :country")
        params["country"] = int(country)
    q = request.args.get("q", "").strip()
    if q:
        conditions.append("r.restaurant_name ILIKE :pattern")
        params["pattern"] = like_pattern(q)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = fetch_all(f"SELECT COUNT(*) AS n FROM restaurants r {where}", **params)[0]["n"]
    rows = fetch_all(
        f"""
        SELECT r.restaurant_id, r.restaurant_name, r.city, c.country_name,
               r.price_range, r.aggregate_rating, r.votes
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        {where}
        ORDER BY r.votes DESC, r.restaurant_id
        LIMIT :limit OFFSET :offset
        """,
        limit=limit,
        offset=offset,
        **params,
    )
    return jsonify(jsonable({"total": total, "limit": limit, "offset": offset, "results": rows}))


@app.route("/api/restaurants/<int:restaurant_id>")
def api_restaurant(restaurant_id):
    """One restaurant with the prediction of each model."""
    rows = fetch_all(
        """
        SELECT r.restaurant_id, r.restaurant_name, r.city, r.cuisines,
               r.average_cost_for_two, r.currency, r.price_range,
               r.has_table_booking, r.has_online_delivery, r.votes,
               r.aggregate_rating, c.country_name
        FROM restaurants r
        JOIN countries c ON c.country_code = r.country_code
        WHERE r.restaurant_id = :rid
        """,
        rid=restaurant_id,
    )
    if not rows:
        return api_error("restaurant not found", 404)
    predictions = fetch_all(
        """
        SELECT model_name, predicted_label, high_probability, actual_label, is_test_row
        FROM predictions
        WHERE restaurant_id = :rid
        ORDER BY model_name
        """,
        rid=restaurant_id,
    )
    return jsonify(jsonable({"restaurant": rows[0], "predictions": predictions}))


@app.route("/api/predict", methods=["POST"])
def api_predict():
    """Prediction for a restaurant described in JSON.

    Example body:
      {"country": "India", "cost": 600, "votes": 120, "price_range": 2,
       "table_booking": false, "online_delivery": true, "cuisines": ["North Indian"]}
    """
    bundle = predictor.load_bundle()
    if bundle is None:
        return api_error("model file not found, run python save_model.py first", 503)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("send a JSON object", 400)
    info = country_cost_info()
    try:
        values = parse_prediction_inputs(data, bundle, info)
    except InputError as problem:
        return api_error(f"invalid value: {problem}", 400)
    return jsonify({"input": values, **run_prediction(values, bundle, info)})


@app.route("/lang/<code>")
def set_language(code):
    """Remember the chosen language in a cookie and go back to the page the visitor came from."""
    if code not in LANGUAGES:
        abort(404)
    target = request.args.get("next", "/")
    # only allow addresses inside this site (no redirect to other websites)
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        target = "/"
    response = redirect(target)
    response.set_cookie("lang", code, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


@app.route("/export/predictions.csv")
def export_predictions():
    """Download all stored predictions as a CSV file."""
    rows = fetch_all(
        """
        SELECT p.restaurant_id, r.restaurant_name, p.model_name, p.predicted_label,
               p.high_probability, p.actual_label, p.is_test_row
        FROM predictions p
        JOIN restaurants r ON r.restaurant_id = p.restaurant_id
        ORDER BY p.model_name, p.restaurant_id
        """
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["restaurant_id", "restaurant_name", "model_name", "predicted_label",
         "high_probability", "actual_label", "is_test_row"]
    )
    for row in rows:
        writer.writerow(
            [row["restaurant_id"], row["restaurant_name"], row["model_name"],
             row["predicted_label"], row["high_probability"], row["actual_label"],
             row["is_test_row"]]
        )
    # utf-8-sig adds a marker so Excel shows special characters correctly
    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=predictions.csv"},
    )


# ---------------------------------------------------------------------------
# Friendly error pages
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(error):
    """Shown when a page or a restaurant does not exist."""
    if request.path.startswith("/api/"):
        return api_error("not found", 404)
    return (
        render_template("error.html", active="", heading=t("err_404_heading"), lines=[t("err_404_line")]),
        404,
    )


@app.errorhandler(405)
def method_not_allowed(error):
    """Wrong HTTP method, for example GET on /api/predict."""
    if request.path.startswith("/api/"):
        return api_error("method not allowed", 405)
    return not_found(error)


@app.errorhandler(OperationalError)
def database_unreachable(error):
    """Shown when PostgreSQL is not running (for example Docker is closed)."""
    if request.path.startswith("/api/"):
        return api_error("database is not reachable", 503)
    lines = [t("err_db_1"), t("err_db_2"), t("err_reload")]
    return render_template("error.html", active="", heading=t("err_db_heading"), lines=lines), 503


@app.errorhandler(ProgrammingError)
def table_missing(error):
    """Shown when a table does not exist yet."""
    if request.path.startswith("/api/"):
        return api_error("a table is missing", 500)
    lines = [t("err_table_1"), t("err_table_2"), t("err_reload")]
    return render_template("error.html", active="", heading=t("err_table_heading"), lines=lines), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
