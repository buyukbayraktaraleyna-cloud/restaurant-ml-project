"""
Data structure experiment: relational columns or JSON documents?

The same restaurants are stored in two ways inside PostgreSQL:
  1. relational: one column per field (like the real `restaurants` table)
  2. document:   one JSONB value per restaurant (like a MongoDB document)
Both copies get about 478,000 rows and comparable indexes, then the same
questions are timed on both.

The real tables are NOT touched. Everything uses temporary tables that are
removed when the connection closes.
"""
import json
import statistics
import time

from sqlalchemy import text

from db import get_engine

COPIES = 50      # how many times every restaurant row is repeated
REPEATS = 20     # how many times each query is timed (the median is reported)


def median_ms(conn, sql, params):
    """Run the query REPEATS times (after one warm-up) and return the median in ms."""
    conn.execute(text(sql), params).fetchall()  # warm-up, not counted
    runs = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        conn.execute(text(sql), params).fetchall()
        runs.append((time.perf_counter() - start) * 1000)
    return statistics.median(runs)


def size_mb(conn, table):
    """Total size of a table including its indexes, in megabytes."""
    return conn.execute(
        text(f"SELECT pg_total_relation_size('{table}') / 1024.0 / 1024.0")
    ).scalar()


def main():
    engine = get_engine()
    with engine.connect() as conn:
        # Real table: only read, to pick a rare country for the queries.
        rare_country = conn.execute(text(
            "SELECT country_code FROM restaurants "
            "GROUP BY country_code ORDER BY COUNT(*) ASC, country_code LIMIT 1"
        )).scalar()

        # 1. Relational copy (one column per field)
        conn.execute(text(
            f"CREATE TEMP TABLE big_relational AS SELECT r.* FROM restaurants r "
            f"CROSS JOIN generate_series(1, {COPIES}) AS g"
        ))
        conn.execute(text("CREATE INDEX ON big_relational (country_code)"))
        conn.execute(text("CREATE INDEX ON big_relational (aggregate_rating)"))

        # 2. Document copy (one JSONB value per restaurant)
        conn.execute(text(
            f"CREATE TEMP TABLE big_json AS SELECT to_jsonb(r) AS doc FROM restaurants r "
            f"CROSS JOIN generate_series(1, {COPIES}) AS g"
        ))
        # B-tree indexes on the extracted fields (comparable to the relational ones)
        conn.execute(text("CREATE INDEX ON big_json ((doc->>'country_code'))"))
        conn.execute(text("CREATE INDEX ON big_json (((doc->>'aggregate_rating')::numeric))"))
        # GIN index: the typical index of a document structure
        conn.execute(text("CREATE INDEX big_json_gin ON big_json USING GIN (doc)"))

        conn.execute(text("ANALYZE big_relational"))
        conn.execute(text("ANALYZE big_json"))
        rows = conn.execute(text("SELECT COUNT(*) FROM big_relational")).scalar()
        print(f"Both copies have {rows} rows. Rarest country_code: {rare_country}\n")

        rel = {"cc": rare_country}
        doc = {"cc": str(rare_country)}

        # (label, relational SQL, JSONB SQL)
        queries = [
            ("country_code = rare country",
             "SELECT * FROM big_relational WHERE country_code = :cc",
             "SELECT doc FROM big_json WHERE doc->>'country_code' = :cc"),
            ("aggregate_rating >= 4.8",
             "SELECT * FROM big_relational WHERE aggregate_rating >= 4.8",
             "SELECT doc FROM big_json WHERE (doc->>'aggregate_rating')::numeric >= 4.8"),
            ("rare country AND rating >= 4.0",
             "SELECT * FROM big_relational WHERE country_code = :cc AND aggregate_rating >= 4.0",
             "SELECT doc FROM big_json WHERE doc->>'country_code' = :cc "
             "AND (doc->>'aggregate_rating')::numeric >= 4.0"),
            ("average rating per country",
             "SELECT country_code, AVG(aggregate_rating), COUNT(*) FROM big_relational GROUP BY country_code",
             "SELECT doc->>'country_code', AVG((doc->>'aggregate_rating')::numeric), COUNT(*) "
             "FROM big_json GROUP BY 1"),
        ]

        print(f"{'Query':<34}{'Relational':>12}{'JSONB':>12}{'JSONB / rel.':>14}")
        print("-" * 72)
        for label, sql_rel, sql_doc in queries:
            t_rel = median_ms(conn, sql_rel, rel if ":cc" in sql_rel else {})
            t_doc = median_ms(conn, sql_doc, doc if ":cc" in sql_doc else {})
            print(f"{label:<34}{t_rel:>9.2f} ms{t_doc:>9.2f} ms{t_doc / t_rel:>13.1f}x")

        # The GIN index answers "contains" questions on the whole document
        t_gin = median_ms(
            conn,
            "SELECT doc FROM big_json WHERE doc @> CAST(:d AS jsonb)",
            {"d": json.dumps({"country_code": rare_country})},
        )
        print(f"\nJSONB with the GIN index, country_code = rare country: {t_gin:.2f} ms")

        # Storage: the JSON documents repeat every field name in every row
        size_rel = size_mb(conn, "big_relational")
        size_doc = size_mb(conn, "big_json")
        print(f"\nTable size including indexes: relational {size_rel:.1f} MB, "
              f"JSONB {size_doc:.1f} MB ({size_doc / size_rel:.1f}x)")
        print(f"\nMedian of {REPEATS} runs per query. Temporary tables are dropped when this script ends.")


if __name__ == "__main__":
    main()
