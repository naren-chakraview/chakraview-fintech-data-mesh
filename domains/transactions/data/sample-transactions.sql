-- ============================================================================
-- Sample Transaction Data for Testing
-- ============================================================================
-- This file contains realistic sample transaction records for testing the
-- Transactions domain semantic layer, RDF transformation, and SPARQL queries.
--
-- Data represents:
-- - Various transaction amounts (500 - 5000 USD)
-- - Different transaction statuses (executed, pending, failed)
-- - Multiple counterparties (Stripe, PayPal, Bank of America, etc.)
-- - Cross-domain customer linking via email and KYC ID
--
-- Purpose: Populate test data for unit tests, integration tests, and
-- manual SPARQL query validation.

-- Create transactions table if not exists
CREATE TABLE IF NOT EXISTS raw_transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(50) UNIQUE NOT NULL,
    customer_email VARCHAR(100) NOT NULL,
    customer_kyc_id VARCHAR(50) NOT NULL,
    counterparty_id VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    transaction_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create counterparties table if not exists
CREATE TABLE IF NOT EXISTS counterparties (
    id SERIAL PRIMARY KEY,
    counterparty_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100),
    type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample transaction data
-- Transaction 1: John Acme → Stripe (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_001', 'john@acme.com', 'kyc_12345', 'stripe', 2500.00, 'executed', '2026-05-30 10:15:00');

-- Transaction 2: Jane TechCorp → PayPal (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_002', 'jane@techcorp.io', 'kyc_67890', 'paypal', 1500.00, 'executed', '2026-05-30 11:30:00');

-- Transaction 3: Alice Finance → Stripe (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_003', 'alice@finance.org', 'kyc_11111', 'stripe', 3200.00, 'executed', '2026-05-30 12:45:00');

-- Transaction 4: Bob Banking → Bank of America (pending)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_004', 'bob@banking.com', 'kyc_22222', 'bofa', 5000.00, 'pending', '2026-05-30 13:20:00');

-- Transaction 5: Carol Investment → Square (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_005', 'carol@invest.net', 'kyc_33333', 'square', 750.50, 'executed', '2026-05-30 14:00:00');

-- Transaction 6: David Commerce → Stripe (failed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_006', 'david@commerce.us', 'kyc_44444', 'stripe', 2200.00, 'failed', '2026-05-30 14:30:00');

-- Transaction 7: Emma Retail → PayPal (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_007', 'emma@retail.co.uk', 'kyc_55555', 'paypal', 890.75, 'executed', '2026-05-30 15:10:00');

-- Transaction 8: Frank Securities → Bank of America (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_008', 'frank@securities.de', 'kyc_66666', 'bofa', 4500.00, 'executed', '2026-05-30 15:45:00');

-- Transaction 9: Grace Analytics → Square (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_009', 'grace@analytics.io', 'kyc_77777', 'square', 1200.00, 'executed', '2026-05-30 16:15:00');

-- Transaction 10: Henry Trading → Stripe (pending)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_010', 'henry@trading.fr', 'kyc_88888', 'stripe', 3100.00, 'pending', '2026-05-30 16:50:00');

-- Transaction 11: Iris Technology → PayPal (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_011', 'iris@technology.jp', 'kyc_99999', 'paypal', 2100.00, 'executed', '2026-05-30 17:20:00');

-- Transaction 12: Jack Manufacturing → Square (executed)
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_012', 'jack@manufacturing.br', 'kyc_00000', 'square', 1600.00, 'executed', '2026-05-30 17:55:00');

-- Edge case: Very high-value transaction ($10,000+) - fraud scoring test
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_013', 'oscar@wealth.com', 'kyc_HIGH01', 'stripe', 10500.00, 'executed', '2026-05-30 18:30:00');

-- Edge case: Failed transaction - settlement reconciliation test
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_014', 'peter@startup.io', 'kyc_START1', 'paypal', 450.25, 'failed', '2026-05-30 19:00:00');

-- Edge case: Long-pending transaction (2+ hours) - delayed transaction detection
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_015', 'quinn@merchant.net', 'kyc_MERC01', 'bofa', 2750.00, 'pending', CURRENT_TIMESTAMP - INTERVAL '3 hours');

-- Edge case: International email (with special character) - character encoding test
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_016', 'sophie.dupont@services.fr', 'kyc_INTL01', 'stripe', 1850.00, 'executed', '2026-05-30 20:15:00');

-- Edge case: Very small amount ($0.01) - minimum transaction test
INSERT INTO raw_transactions (transaction_id, customer_email, customer_kyc_id, counterparty_id, amount, status, transaction_date)
VALUES ('txn_017', 'tom@micro.co', 'kyc_TINY01', 'square', 0.01, 'executed', '2026-05-30 20:45:00');

-- Insert counterparty reference data
INSERT INTO counterparties (counterparty_id, name, type)
VALUES ('stripe', 'Stripe Inc.', 'processor');

INSERT INTO counterparties (counterparty_id, name, type)
VALUES ('paypal', 'PayPal Holdings', 'processor');

INSERT INTO counterparties (counterparty_id, name, type)
VALUES ('bofa', 'Bank of America', 'bank');

INSERT INTO counterparties (counterparty_id, name, type)
VALUES ('square', 'Square Inc.', 'processor');

-- Verify data inserted
SELECT 'Sample transactions loaded successfully. Transaction count:' AS status, COUNT(*) FROM raw_transactions;
SELECT 'Counterparties loaded. Count:' AS status, COUNT(*) FROM counterparties;
