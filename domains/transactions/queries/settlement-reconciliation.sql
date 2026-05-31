-- ============================================================================
-- Query: Settlement Reconciliation
-- ============================================================================
-- Purpose: Identify and reconcile transactions by settlement status.
--          Useful for identifying stuck or delayed settlements.
--
-- Use Case:
-- - Clearing operations team tracking settlement delays
-- - Reconciliation team identifying discrepancies
-- - Risk monitoring for blocked transactions
--
-- Output Columns:
-- - transaction_id: Unique transaction identifier
-- - counterparty_id: Which processor/bank handled the transaction
-- - amount: Transaction amount
-- - transaction_status: Execution status (executed, failed, pending)
-- - settlement_status: Clearing status (if available)
-- - days_pending: How long settlement has been pending
-- - transaction_date: Original transaction timestamp
--
-- Example:
-- SELECT * FROM settlement_reconciliation
-- WHERE settlement_status = 'pending' AND days_pending > 2;
-- ============================================================================

SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    rt.amount,
    rt.status AS transaction_status,
    rt.transaction_date,
    CURRENT_TIMESTAMP - rt.transaction_date AS time_since_transaction,
    EXTRACT(DAY FROM CURRENT_TIMESTAMP - rt.transaction_date) AS days_pending,
    rt.created_at AS loaded_at
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
WHERE rt.status != 'executed'  -- Focus on non-executed transactions
ORDER BY rt.transaction_date ASC
LIMIT 100;

-- Settlement status breakdown by counterparty
SELECT
    rt.counterparty_id,
    cp.name AS counterparty_name,
    rt.status,
    COUNT(*) AS transaction_count,
    SUM(rt.amount) AS total_amount,
    AVG(rt.amount) AS avg_amount,
    MIN(rt.transaction_date) AS oldest_transaction,
    MAX(rt.transaction_date) AS newest_transaction
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
GROUP BY rt.counterparty_id, cp.name, rt.status
ORDER BY rt.counterparty_id, rt.status;

-- Pending transactions exceeding SLA (e.g., > 1 hour pending)
-- Useful for alerting
SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    rt.amount,
    CURRENT_TIMESTAMP - rt.transaction_date AS time_pending,
    ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - rt.transaction_date)) / 3600, 2) AS hours_pending
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
WHERE rt.status = 'pending'
  AND CURRENT_TIMESTAMP - rt.transaction_date > INTERVAL '1 hour'
ORDER BY rt.transaction_date ASC;

-- Failed transaction analysis (potential issues requiring investigation)
SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.customer_kyc_id,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    rt.amount,
    rt.transaction_date,
    rt.created_at,
    EXTRACT(DAY FROM CURRENT_TIMESTAMP - rt.transaction_date) AS days_since_failure
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
WHERE rt.status = 'failed'
ORDER BY rt.transaction_date DESC
LIMIT 50;

-- Reconciliation summary: Expected vs. cleared
-- Shows which transactions are at risk of settlement failure
SELECT
    DATE(rt.transaction_date) AS settlement_date,
    COUNT(*) AS total_transactions,
    COUNT(CASE WHEN rt.status = 'executed' THEN 1 END) AS executed,
    COUNT(CASE WHEN rt.status = 'pending' THEN 1 END) AS pending,
    COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) AS failed,
    SUM(CASE WHEN rt.status = 'executed' THEN rt.amount ELSE 0 END) AS executed_amount,
    SUM(CASE WHEN rt.status = 'pending' THEN rt.amount ELSE 0 END) AS pending_amount,
    SUM(CASE WHEN rt.status = 'failed' THEN rt.amount ELSE 0 END) AS failed_amount
FROM raw_transactions rt
GROUP BY DATE(rt.transaction_date)
ORDER BY DATE(rt.transaction_date) DESC;
