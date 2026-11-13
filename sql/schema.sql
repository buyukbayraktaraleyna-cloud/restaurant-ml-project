-- Schema for the Zomato restaurant classification project

-- Drop old tables so the script can be re-run safely
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS countries;

-- Lookup table: maps a country code to a country name
CREATE TABLE countries (
    country_code INTEGER PRIMARY KEY,
    country_name VARCHAR(60) NOT NULL
);

-- Main table: one row per restaurant
CREATE TABLE restaurants (
    restaurant_id        INTEGER PRIMARY KEY,
    restaurant_name      VARCHAR(255) NOT NULL,
    country_code         INTEGER NOT NULL REFERENCES countries(country_code),
    city                 VARCHAR(100) NOT NULL,
    address              TEXT,
    locality             TEXT,
    locality_verbose     TEXT,
    longitude            DOUBLE PRECISION,
    latitude             DOUBLE PRECISION,
    cuisines             TEXT,            -- comma-separated list, kept as raw text
    average_cost_for_two INTEGER,
    currency             VARCHAR(60),
    has_table_booking    BOOLEAN,
    has_online_delivery  BOOLEAN,
    is_delivering_now    BOOLEAN,
    switch_to_order_menu BOOLEAN,
    price_range          SMALLINT CHECK (price_range BETWEEN 1 AND 4),
    aggregate_rating     NUMERIC(2,1) CHECK (aggregate_rating BETWEEN 0 AND 5),
    rating_color         VARCHAR(30),
    rating_text          VARCHAR(30),
    votes                INTEGER
);

-- Indexes to speed up filtering by country and by rating
CREATE INDEX idx_restaurants_country ON restaurants(country_code);
CREATE INDEX idx_restaurants_rating  ON restaurants(aggregate_rating);