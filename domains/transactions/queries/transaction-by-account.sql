-- ============================================================================
-- Query: Transactions by Account
-- ============================================================================
-- Purpose: Find all transactions associated with a specific account/customer
--          along with settlement status and counterparty information.
--
-- Use Case:
-- - Customer service looking up account transaction history
-- - Analytics team analyzing customer transaction patterns
-- - Fraud detection reviewing customer activity
--
-- Parameters:
-- - customer_email: Email of the customer to look up
-- - customer_kyc_id: KYC identifier for the customer
--
-- Output Columns:
-- - transaction_id: Unique transaction identifier
-- - customer_email: Customer email (for verification)
-- - counterparty_id: Receiving counterparty (processor, merchant, bank)
-- - amount: Transaction amount in USD
-- - status: Transaction execution status (executed, failed, pending)
-- - settlement_status: Clearing status (cleared, pending, on-hold)
-- - transaction_date: When transaction occurred
--
-- Example:
-- SELECT * FROM raw_transactions
-- WHERE customer_email = 'john@acme.com' AND customer_kyc_id = 'kyc_12345'
-- ORDER BY transaction_date DESC;
-- ============================================================================

SELECT
    rt.transaction_id,
    rt.customer_email,
    rt.customer_kyc_id,
    rt.counterparty_id,
    cp.name AS counterparty_name,
    cp.type AS counterparty_type,
    rt.amount,
    rt.status,
    rt.transaction_date,
    rt.created_at AS loaded_at
FROM raw_transactions rt
LEFT JOIN counterparties cp ON rt.counterparty_id = cp.counterparty_id
WHERE rt.customer_email = '{{ customer_email }}'
  AND rt.customer_kyc_id = '{{ customer_kyc_id }}'
ORDER BY rt.transaction_date DESC
LIMIT 100;

-- Aggregated view: Transaction summary by account
-- Returns total transaction value, counts by status
SELECT
    rt.customer_email,
    rt.customer_kyc_id,
    COUNT(*) AS transaction_count,
    SUM(rt.amount) AS total_amount,
    COUNT(CASE WHEN rt.status = 'executed' THEN 1 END) AS executed_count,
    COUNT(CASE WHEN rt.status = 'pending' THEN 1 END) AS pending_count,
    COUNT(CASE WHEN rt.status = 'failed' THEN 1 END) AS failed_count,
    MIN(rt.transaction_date) AS first_transaction,
    MAX(rt.transaction_date) AS last_transaction
FROM raw_transactions rt
WHERE rt.customer_email = '{{ customer_email }}'
  AND rt.customer_kyc_id = '{{ customer_kyc_id }}'
GROUP BY rt.customer_email, rt.customer_kyc_id;

-- Variant: All transactions for an account with daily breakdown
SELECT
    DATE(rt.transaction_date) AS transaction_day,
    COUNT(*) AS daily_count,
    SUM(rt.amount) AS daily_total,
    COUNT(DISTINCT rt.counterparty_id) AS unique_counterparties
FROM raw_transactions rt
WHERE rt.customer_email = '{{ customer_email }}'
  AND rt.customer_kyc_id = '{{ customer_kyc_id }}'
GROUP BY DATE(rt.transaction_date)
ORDER BY transaction_day DESC;
