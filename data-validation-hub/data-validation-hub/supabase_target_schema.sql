-- ============================================================================
-- RETAIL UNIFIED SALES MODEL — Target Schema
-- Supabase (PostgreSQL)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ── Dimension: Stores ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_stores (
    store_id        VARCHAR(20)   PRIMARY KEY,
    store_name      VARCHAR(100)  NOT NULL,
    region          VARCHAR(50)   NOT NULL,
    city            VARCHAR(50)   NOT NULL,
    address         VARCHAR(200),
    manager         VARCHAR(100),
    opening_date    DATE,
    sqm             INTEGER,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_dim_stores_region ON dim_stores (region);
CREATE INDEX idx_dim_stores_city   ON dim_stores (city);


-- ── Dimension: Customers ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id     UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255)  NOT NULL,
    name            VARCHAR(150),
    phone           VARCHAR(30),
    loyalty_tier    VARCHAR(20),
    total_spend     DECIMAL(12,2) DEFAULT 0,
    last_purchase   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_dim_customers_email ON dim_customers (lower(email));
CREATE INDEX idx_dim_customers_tier         ON dim_customers (loyalty_tier);


-- ── Dimension: Products ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dim_products (
    product_id      VARCHAR(50)   PRIMARY KEY,
    product_name    VARCHAR(200),
    category        VARCHAR(100),
    supplier_id     VARCHAR(50),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_dim_products_category ON dim_products (category);


-- ── Fact: Sales ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fact_sales (
    sale_id         UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    store_id        VARCHAR(20)   NOT NULL REFERENCES dim_stores(store_id),
    product_id      VARCHAR(50)   NOT NULL REFERENCES dim_products(product_id),
    customer_id     UUID          REFERENCES dim_customers(customer_id),
    quantity        INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price      DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0),
    total_amount    DECIMAL(12,2) NOT NULL,
    sale_date       TIMESTAMPTZ   NOT NULL,
    channel         VARCHAR(20)   NOT NULL CHECK (channel IN ('pos','ecommerce','marketplace')),
    payment_type    VARCHAR(30),
    currency        VARCHAR(3)    NOT NULL DEFAULT 'EUR',
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_fact_sales_date       ON fact_sales (sale_date);
CREATE INDEX idx_fact_sales_store      ON fact_sales (store_id);
CREATE INDEX idx_fact_sales_product    ON fact_sales (product_id);
CREATE INDEX idx_fact_sales_customer   ON fact_sales (customer_id);
CREATE INDEX idx_fact_sales_channel    ON fact_sales (channel);
CREATE INDEX idx_fact_sales_date_store ON fact_sales (sale_date, store_id);
