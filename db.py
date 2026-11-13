"""Shared database connection settings for the project."""

from sqlalchemy import create_engine

# Connection settings of the PostgreSQL container started with docker compose
DB_USER = "student"
DB_PASSWORD = "student123"  # local development password only
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "restaurant_ml"


def get_engine():
    """Create and return a SQLAlchemy engine connected to PostgreSQL."""
    url = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    return create_engine(url)