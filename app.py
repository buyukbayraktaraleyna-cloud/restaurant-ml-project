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
    /lang/<code>            choose the language (en, tr, de, ar, zh)

The HTML pages are in the templates folder, the CSS and JavaScript are in the static folder.
The panel only reads from the database, it never changes any data.
"""

import csv
import io
from math import ceil
from urllib.parse import urlencode

from flask import Flask, Response, abort, redirect, render_template, request
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

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
    return (
        render_template("error.html", active="", heading=t("err_404_heading"), lines=[t("err_404_line")]),
        404,
    )


@app.errorhandler(OperationalError)
def database_unreachable(error):
    """Shown when PostgreSQL is not running (for example Docker is closed)."""
    lines = [t("err_db_1"), t("err_db_2"), t("err_reload")]
    return render_template("error.html", active="", heading=t("err_db_heading"), lines=lines), 503


@app.errorhandler(ProgrammingError)
def table_missing(error):
    """Shown when a table does not exist yet."""
    lines = [t("err_table_1"), t("err_table_2"), t("err_reload")]
    return render_template("error.html", active="", heading=t("err_table_heading"), lines=lines), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
