"""Small web panel that shows the model results stored in PostgreSQL (step 13).

Run it with:   python app.py
Then open:     http://127.0.0.1:5000

The panel only reads from the database, it never changes any data.
"""

from flask import Flask, request
from jinja2 import DictLoader, Environment
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from db import get_engine

app = Flask(__name__)
engine = get_engine()


# ---------------------------------------------------------------------------
# HTML templates (kept in this file so the whole panel is a single script)
# ---------------------------------------------------------------------------

BASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}{% endblock %} - Restaurant Rating Panel</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f7f9; --card: #ffffff; --text: #1f2933; --muted: #667085;
    --line: #e4e7ec; --accent: #2b6cb0; --good: #2f855a; --bad: #c53030;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14181d; --card: #1d232b; --text: #e6e9ee; --muted: #9aa4b2;
      --line: #2c3541; --accent: #63a4e8; --good: #5fcf8f; --bad: #f08a8a;
    }
  }
  body { margin: 0; font-family: system-ui, "Segoe UI", Arial, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  header { background: var(--card); border-bottom: 1px solid var(--line); }
  .wrap { max-width: 960px; margin: 0 auto; padding: 0 20px; }
  nav { display: flex; gap: 20px; align-items: center; padding: 14px 0; flex-wrap: wrap; }
  nav strong { margin-right: auto; }
  nav a { color: var(--muted); text-decoration: none; font-weight: 600; }
  nav a.active { color: var(--accent); }
  main { padding: 24px 0 48px; }
  h1 { font-size: 1.6rem; margin: 0 0 6px; }
  h2 { font-size: 1.15rem; margin: 0 0 8px; }
  h3 { font-size: 1rem; margin: 16px 0 6px; }
  .sub { color: var(--muted); margin: 0 0 22px; }
  .card { background: var(--card); border: 1px solid var(--line);
          border-radius: 12px; padding: 18px 20px; margin-bottom: 18px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
           gap: 14px; margin-bottom: 18px; }
  .stats .card { margin-bottom: 0; }
  .num { font-size: 1.7rem; font-weight: 700; }
  .label { color: var(--muted); font-size: .9rem; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line);
           vertical-align: middle; }
  th { color: var(--muted); font-size: .85rem; font-weight: 600; }
  .table-scroll { overflow-x: auto; }
  .bar { height: 6px; background: var(--line); border-radius: 3px;
         margin-top: 4px; min-width: 70px; }
  .bar span { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
  .matrix { max-width: 340px; }
  .matrix th, .matrix td { text-align: center; }
  .good { color: var(--good); font-weight: 600; }
  .bad { color: var(--bad); font-weight: 600; }
  .muted { color: var(--muted); }
  .pill { display: inline-block; padding: 2px 10px; border-radius: 999px;
          border: 1px solid var(--line); font-size: .85rem; color: var(--muted); }
  input[type=text] { padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px;
                     background: var(--bg); color: var(--text); width: min(420px, 100%);
                     font-size: 1rem; }
  button { padding: 10px 16px; border: 0; border-radius: 8px; background: #2b6cb0;
           color: #ffffff; font-size: 1rem; cursor: pointer; }
  .tabs a { margin-right: 16px; color: var(--accent); text-decoration: none; }
  .tabs a.current { font-weight: 700; text-decoration: underline; }
  code { background: var(--bg); padding: 1px 6px; border-radius: 4px; }
</style>
</head>
<body>
<header><div class="wrap"><nav>
  <strong>Restaurant Rating Panel</strong>
  <a href="/" class="{{ 'active' if active == 'home' }}">Results</a>
  <a href="/search" class="{{ 'active' if active == 'search' }}">Search</a>
  <a href="/mistakes" class="{{ 'active' if active == 'mistakes' }}">Mistakes</a>
</nav></div></header>
<main><div class="wrap">
{% block content %}{% endblock %}
</div></main>
</body>
</html>
"""

INDEX_TEMPLATE = """{% extends "base.html" %}
{% block title %}Results{% endblock %}
{% block content %}
<h1>Model results</h1>
<p class="sub">Everything on this page is read live from PostgreSQL.</p>

<div class="stats">
  <div class="card"><div class="num">{{ n_restaurants }}</div>
    <div class="label">restaurants in the database</div></div>
  <div class="card"><div class="num">{{ n_rated }}</div>
    <div class="label">rated restaurants used by the models</div></div>
  <div class="card"><div class="num">{{ n_predictions }}</div>
    <div class="label">predictions stored</div></div>
</div>

{% if metrics %}
<div class="card">
  <h2>Test-set metrics</h2>
  <div class="table-scroll"><table>
    <tr><th>Model</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th>
        <th>Training time</th></tr>
    {% for m in metrics %}
    <tr>
      <td><strong>{{ m.model_name }}</strong></td>
      {% for key in ["accuracy", "precision_score", "recall_score", "f1_score"] %}
      <td>{{ "%.3f"|format(m[key]) }}
        <div class="bar"><span style="width: {{ '%.1f'|format(m[key] * 100) }}%"></span></div></td>
      {% endfor %}
      <td>{{ "%.3f"|format(m.train_seconds) }} s</td>
    </tr>
    {% endfor %}
  </table></div>
  <p class="muted">Measured on {{ metrics[0].test_rows }} restaurants that were not used for training.</p>
</div>

<div class="card">
  <h2>Confusion matrices</h2>
  <p class="muted">Rows are the real class, columns are the predicted class
    (1 means a rating of 3.5 or higher).</p>
  {% for name, mx in matrices.items() %}
  <h3>{{ name }}</h3>
  <table class="matrix">
    <tr><th></th><th>Predicted 0</th><th>Predicted 1</th></tr>
    <tr><th>Real 0</th><td>{{ mx[0][0] }}</td><td>{{ mx[0][1] }}</td></tr>
    <tr><th>Real 1</th><td>{{ mx[1][0] }}</td><td>{{ mx[1][1] }}</td></tr>
  </table>
  {% endfor %}
</div>
{% else %}
<div class="card">No results found. Run <code>python save_results.py</code> first.</div>
{% endif %}
{% endblock %}
"""

SEARCH_TEMPLATE = """{% extends "base.html" %}
{% block title %}Search{% endblock %}
{% block content %}
<h1>Search a restaurant</h1>
<p class="sub">Type a restaurant name to see its real rating and what each model predicted.</p>

<form method="get" action="/search" class="card">
  <input type="text" name="q" value="{{ q }}" placeholder="for example: Subway" autofocus>
  <button type="submit">Search</button>
</form>

{% if q %}
  {% if results %}
    <p class="muted">Found {{ results|length }} matching restaurant(s), most votes first (maximum 10).</p>
    {% for r in results %}
    <div class="card">
      <h2>{{ r.restaurant_name }}</h2>
      <p class="muted">{{ r.city }}, {{ r.country_name }} &middot; {{ r.votes }} votes</p>
      <p>Real rating: <strong>{{ r.aggregate_rating }}</strong>
        {% if r.aggregate_rating > 0 %}
        <span class="pill">{{ 'high rated (3.5 or more)' if r.aggregate_rating >= 3.5 else 'below 3.5' }}</span>
        {% endif %}
      </p>
      {% if r.predictions %}
      <div class="table-scroll"><table>
        <tr><th>Model</th><th>Prediction</th><th>Probability of a high rating</th>
            <th>Result</th><th>Row used for</th></tr>
        {% for p in r.predictions %}
        <tr>
          <td>{{ p.model_name }}</td>
          <td>{{ 'high rated' if p.predicted_label == 1 else 'not high rated' }}</td>
          <td>{{ "%.1f"|format(p.high_probability * 100) }}%</td>
          <td class="{{ 'good' if p.predicted_label == p.actual_label else 'bad' }}">
            {{ 'correct' if p.predicted_label == p.actual_label else 'wrong' }}</td>
          <td>{{ 'test' if p.is_test_row else 'training' }}</td>
        </tr>
        {% endfor %}
      </table></div>
      <p class="muted">Rows used for "training" were seen by the model while it was learning.
        Only "test" rows show how well the model works on restaurants it has not seen.</p>
      {% else %}
      <p class="muted">This restaurant has no rating yet, so the models made no prediction for it.</p>
      {% endif %}
    </div>
    {% endfor %}
  {% else %}
    <div class="card">No restaurant found for "{{ q }}".</div>
  {% endif %}
{% endif %}
{% endblock %}
"""

MISTAKES_TEMPLATE = """{% extends "base.html" %}
{% block title %}Mistakes{% endblock %}
{% block content %}
<h1>Most confident mistakes</h1>
<p class="sub">Test restaurants where the model was wrong even though it was very sure.</p>

<div class="card tabs">
  {% for name in models %}
  <a href="/mistakes?model={{ name|urlencode }}" class="{{ 'current' if name == model }}">{{ name }}</a>
  {% endfor %}
</div>

{% if rows %}
<div class="card">
  <div class="table-scroll"><table>
    <tr><th>Restaurant</th><th>City</th><th>Real rating</th><th>Predicted</th>
        <th>Probability of a high rating</th></tr>
    {% for r in rows %}
    <tr>
      <td>{{ r.restaurant_name }}</td>
      <td>{{ r.city }}</td>
      <td>{{ r.aggregate_rating }}</td>
      <td>{{ 'high rated' if r.predicted_label == 1 else 'not high rated' }}</td>
      <td>{{ "%.1f"|format(r.high_probability * 100) }}%</td>
    </tr>
    {% endfor %}
  </table></div>
  <p class="muted">Restaurants whose real rating is close to the 3.5 threshold are the hardest to classify.</p>
</div>
{% else %}
<div class="card">No mistakes to show. Run <code>python save_results.py</code> first.</div>
{% endif %}
{% endblock %}
"""

ERROR_TEMPLATE = """{% extends "base.html" %}
{% block title %}Error{% endblock %}
{% block content %}
<h1>{{ heading }}</h1>
<div class="card">
  <ol>
    {% for line in lines %}<li>{{ line }}</li>{% endfor %}
  </ol>
</div>
{% endblock %}
"""

env = Environment(
    loader=DictLoader(
        {
            "base.html": BASE_TEMPLATE,
            "index.html": INDEX_TEMPLATE,
            "search.html": SEARCH_TEMPLATE,
            "mistakes.html": MISTAKES_TEMPLATE,
            "error.html": ERROR_TEMPLATE,
        }
    ),
    autoescape=True,  # escapes user input such as the search text
)


def render(name, **context):
    """Render one of the templates above."""
    return env.get_template(name).render(**context)


def fetch_all(sql, **params):
    """Run a read-only SQL query and return the rows as a list of dictionaries."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row) for row in result.mappings()]


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

    return render("index.html", active="home", metrics=metrics, matrices=matrices, **counts)


@app.route("/search")
def search():
    """Find restaurants by name and show the prediction of each model."""
    q = request.args.get("q", "").strip()
    results = []

    if q:
        # Escape the LIKE wildcards so the user text is searched literally
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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
            pattern=f"%{escaped}%",
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

    return render("search.html", active="search", q=q, results=results)


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
            SELECT r.restaurant_name, r.city, r.aggregate_rating,
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

    return render("mistakes.html", active="mistakes", models=models, model=model, rows=rows)


# ---------------------------------------------------------------------------
# Friendly error pages
# ---------------------------------------------------------------------------


@app.errorhandler(OperationalError)
def database_unreachable(error):
    """Shown when PostgreSQL is not running (for example Docker is closed)."""
    lines = [
        "Open Docker Desktop and wait until the engine is running.",
        "Run docker compose up -d in the project folder.",
        "Reload this page.",
    ]
    return render("error.html", active="", heading="Cannot reach the database", lines=lines), 503


@app.errorhandler(ProgrammingError)
def table_missing(error):
    """Shown when a table does not exist yet."""
    lines = [
        "Run python load_data.py to fill the restaurants and countries tables.",
        "Run python save_results.py to create and fill the results tables.",
        "Reload this page.",
    ]
    return render("error.html", active="", heading="A table is missing", lines=lines), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
