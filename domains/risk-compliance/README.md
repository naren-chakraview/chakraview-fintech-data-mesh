# Risk/Compliance Domain

Real-time fraud detection and regulatory compliance scoring.

## Data Products

- **risk-scores** — Fraud scores + KYC/AML verdicts
  - Tables: `fraud_scores`, `kyc_verdicts`
  - Freshness: 10 minutes
  - Retention: 10 years (AML requirement)

## Key Tables

- `fraud_scores` — Real-time fraud risk evaluation per transaction
- `kyc_verdicts` — KYC and AML verification results

## SLA

- Freshness: 10 minutes
- Availability: 99.99%
