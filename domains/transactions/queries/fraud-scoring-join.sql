-- ============================================================================
-- Query: Fraud Scoring Data Join
-- ============================================================================
-- Purpose: Join transaction data with customer and counterparty information
--          to generate features for fraud detection models.
--
-- Use Case:
-- - Fraud detection team building risk scoring features
-- - ML pipeline input for transaction classification (fraudulent vs. legitimate)
-- - Risk compliance team investigating suspicious transactions
--
-- Output Columns:
-- - transaction_id: Unique transaction identifier
-- - customer_email: Customer contact (for verification/follow-up)
-- - customer_kyc_id: KYC reference
-- - counterparty_id: Which processor/merchant (pattern indicator)
-- - amount: Transaction amount (anomaly detection feature)
-- - hours_since_last: Time since last transaction by this customer (velocity)
-- - transaction_count_24h: How many transactions in last 24 hours
-- - transaction_count_30d: How many transactions in last 30 days
-- - transaction_date: Timestamp for timestamp-based features
--
-- Example:
-- Used as input to fraud scoring model:
--   SELECT * FROM fraud_scoring_features
--   WHERE risk_flag = true
--   ORDER BY transaction_date DESC;
-- ============================================================================

-- Main fraud scoring query: Rich feature set for ML models
SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.customer_kyc_id,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    cp.type AS counterparty_type,
    rt.amount,
    rt.status AS transaction_status,
    rt.transaction_date,
    -- Customer transaction history features
    COUNT(*) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
        ORDER BY rt.transaction_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS customer_transaction_lifetime_count,
    COUNT(*) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
        ORDER BY rt.transaction_date
        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
    ) AS customer_future_transaction_count,
    -- Transaction velocity features (time-based)
    LAG(rt.transaction_date) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
        ORDER BY rt.transaction_date
    ) AS last_transaction_date,
    EXTRACT(EPOCH FROM (rt.transaction_date - LAG(rt.transaction_date) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
        ORDER BY rt.transaction_date
    ))) / 3600 AS hours_since_last_transaction,
    -- Counterparty patterns
    COUNT(*) OVER (
        PARTITION BY rt.counterparty_id
        ORDER BY rt.transaction_date
    ) AS counterparty_transaction_total,
    -- Anomaly detection: average amount by customer
    AVG(rt.amount) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
    ) AS customer_avg_amount,
    STDDEV(rt.amount) OVER (
        PARTITION BY rt.customer_email, rt.customer_kyc_id
    ) AS customer_stddev_amount,
    -- Flag potentially suspicious transactions
    CASE
        WHEN rt.amount > 5000 THEN true
        WHEN rt.status = 'failed' THEN true
        ELSE false
    END AS risk_flag
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
ORDER BY rt.transaction_date DESC;

-- Simplified view: High-risk transactions only
SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    rt.amount,
    rt.status,
    rt.transaction_date,
    CASE
        WHEN rt.amount > 5000 THEN 'HIGH_AMOUNT'
        WHEN rt.status = 'failed' THEN 'FAILED_TXN'
        WHEN rt.status = 'pending' AND (CURRENT_TIMESTAMP - rt.transaction_date) > INTERVAL '2 hours' THEN 'DELAYED'
        ELSE 'NORMAL'
    END AS risk_category
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
WHERE rt.amount > 5000 OR rt.status = 'failed'
ORDER BY rt.transaction_date DESC;

-- Time-based velocity analysis (transactions per customer per hour)
-- Useful for detecting account takeover or card testing
SELECT
    rt.customer_email,
    rt.customer_kyc_id,
    DATE_TRUNC('hour', rt.transaction_date) AS transaction_hour,
    COUNT(*) AS transactions_per_hour,
    SUM(rt.amount) AS total_amount_per_hour,
    MAX(rt.amount) AS max_amount,
    COUNT(DISTINCT rt.counterparty_id) AS unique_counterparties
FROM raw_transactions rt
GROUP BY rt.customer_email, rt.customer_kyc_id, DATE_TRUNC('hour', rt.transaction_date)
HAVING COUNT(*) > 3  -- Flag if >3 transactions in one hour
ORDER BY DATE_TRUNC('hour', rt.transaction_date) DESC;

-- Counterparty risk analysis: Transactions by processor/merchant
SELECT
    rt.counterparty_id,
    cp.name AS counterparty_name,
    cp.type AS counterparty_type,
    COUNT(*) AS total_transactions,
    COUNT(CASE WHEN rt.status = 'executed' THEN 1 END) AS successful_count,
    COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) AS failed_count,
    ROUND(100.0 * COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) / COUNT(*), 2) AS failure_rate,
    SUM(rt.amount) AS total_volume,
    AVG(rt.amount) AS avg_amount,
    MIN(rt.amount) AS min_amount,
    MAX(rt.amount) AS max_amount,
    COUNT(DISTINCT rt.customer_email) AS unique_customers
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
GROUP BY rt.counterparty_id, cp.name, cp.type
ORDER BY failed_count DESC, total_transactions DESC;

-- Feature engineering: Customer behavioral profiles for fraud scoring
SELECT
    rt.customer_email,
    rt.customer_kyc_id,
    COUNT(*) AS total_transactions,
    COUNT(DISTINCT rt.counterparty_id) AS unique_counterparties,
    COUNT(DISTINCT DATE(rt.transaction_date)) AS active_days,
    SUM(rt.amount) AS total_spend,
    AVG(rt.amount) AS avg_transaction,
    STDDEV(rt.amount) AS amount_volatility,
    MAX(rt.amount) AS max_transaction,
    MIN(rt.transaction_date) AS first_transaction_date,
    MAX(rt.transaction_date) AS last_transaction_date,
    COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) AS failed_transactions,
    ROUND(100.0 * COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) / COUNT(*), 2) AS failure_rate
FROM raw_transactions rt
GROUP BY rt.customer_email, rt.customer_kyc_id
ORDER BY failure_rate DESC, total_spend DESC;
