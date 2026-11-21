"""
Index experiment: how much does an index change query time?

The real tables are NOT touched. The script makes two temporary copies of
the restaurants table, blows them up to about 478,000 rows, puts indexes on
one copy only, and times the same queries on both. Temporary tables vanish
automatically when the connection closes.
"""
import statistics
import time

from sqlalchemy import text

from db import get_engine

COPIES = 50      # how many times every restaurant row is repeated
REPEATS = 20     # how many times each query is timed (the median is reported)


def timed_ms(conn, sql, params):
    """Run the query once and return the time in milliseconds."""
    start = time.perf_counter()
    conn.execute(text(sql), params).fetchall()
    return (time.perf_counter() - start) * 1000


def plan_type(conn, sql, params):
    """Return the main scan type PostgreSQL chose (Seq Scan, Index Scan...)."""
    rows = conn.execute(text("EXPLAIN " + sql), params).fetchall()
    plan = " ".join(r[0] for r in rows)
    for name in ("Bitmap Index Scan", "Index Only Scan", "Index Scan", "Seq Scan"):
        if name in plan:
            return name
    return "other"


def main():
    engine = get_engine()
    with engine.connect() as conn:
        # Real table: only read, to pick values for the queries.
        real_rows = conn.execute(text("SELECT COUNT(*) FROM restaurants")).scalar()
        rare_country = conn.execute(text(
            "SELECT country_code FROM restaurants "
            "GROUP BY country_code ORDER BY COUNT(*) ASC, country_code LIMIT 1"
        )).scalar()
        print(f"Real table: {real_rows} rows. Rarest country_code: {rare_country}")

        # Two temporary copies, each COPIES times larger than the real table.
        for name in ("big_no_index", "big_with_index"):
            conn.execute(text(
                f"CREATE TEMP TABLE {name} AS "
                f"SELECT r.* FROM restaurants r "
                f"CROSS JOIN generate_series(1, {COPIES}) AS g"
            ))
        conn.execute(text("CREATE INDEX ON big_with_index (country_code)"))
        conn.execute(text("CREATE INDEX ON big_with_index (aggregate_rating)"))
        conn.execute(text("ANALYZE big_no_index"))
        conn.execute(text("ANALYZE big_with_index"))
        big_rows = conn.execute(text("SELECT COUNT(*) FROM big_no_index")).scalar()
        print(f"Temporary copies: {big_rows} rows each\n")

        queries = {
            "country_code = rare country":
                "SELECT * FROM {t} WHERE country_code = :cc",
            "aggregate_rating >= 4.8":
                "SELECT * FROM {t} WHERE aggregate_rating >= 4.8",
            "rare country AND rating >= 4.0":
                "SELECT * FROM {t} WHERE country_code = :cc AND aggregate_rating >= 4.0",
        }
        params = {"cc": rare_country}

        print(f"{'Query':<34}{'No index':>12}{'With index':>13}{'Speed-up':>10}   Plan (with index)")
        print("-" * 92)
        for label, template in queries.items():
            results = {}
            for table in ("big_no_index", "big_with_index"):
                sql = template.format(t=table)
                timed_ms(conn, sql, params)  # warm-up run, not counted
                runs = [timed_ms(conn, sql, params) for _ in range(REPEATS)]
                results[table] = statistics.median(runs)
            plan = plan_type(conn, template.format(t="big_with_index"), params)
            slow, fast = results["big_no_index"], results["big_with_index"]
            print(f"{label:<34}{slow:>9.2f} ms{fast:>10.2f} ms{slow / fast:>9.1f}x   {plan}")

        print(f"\nMedian of {REPEATS} runs per query. Temporary tables are dropped when this script ends.")


if __name__ == "__main__":
    main()
