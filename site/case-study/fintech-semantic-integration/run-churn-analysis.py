#!/usr/bin/env python3
"""
Run churn analysis federated query across all three domains.

Usage:
    python run-churn-analysis.py [--format json|table]
"""

import sys
import argparse
import os
from pathlib import Path

# Add parent directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from federated_query_client import FederatedQueryClient


def main():
    parser = argparse.ArgumentParser(
        description="Execute churn risk analysis across fintech semantic mesh domains"
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)"
    )
    parser.add_argument(
        "--accounts-url",
        default="http://localhost:3030/accounts/sparql",
        help="Accounts domain SPARQL endpoint URL"
    )
    parser.add_argument(
        "--transactions-url",
        default="http://localhost:3031/transactions/sparql",
        help="Transactions domain SPARQL endpoint URL"
    )
    parser.add_argument(
        "--risk-url",
        default="http://localhost:3032/risk_compliance/sparql",
        help="Risk/Compliance domain SPARQL endpoint URL"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Query timeout in seconds (default: 30)"
    )

    args = parser.parse_args()

    # Configure endpoints
    endpoints = {
        "accounts": args.accounts_url,
        "transactions": args.transactions_url,
        "risk": args.risk_url,
    }

    # Create client
    client = FederatedQueryClient(endpoints, timeout=args.timeout)

    # Check endpoint availability
    print("Checking endpoint availability...", file=sys.stderr)
    status = client.check_endpoints()
    all_available = all(status.values())

    for domain, available in status.items():
        status_str = "✓ Available" if available else "✗ Unavailable"
        print(f"  {domain:15} {status_str}", file=sys.stderr)

    if not all_available:
        print("\nError: Not all endpoints are available.", file=sys.stderr)
        print("Please ensure all domain SPARQL endpoints are running:", file=sys.stderr)
        print(f"  - Accounts: {endpoints['accounts']}", file=sys.stderr)
        print(f"  - Transactions: {endpoints['transactions']}", file=sys.stderr)
        print(f"  - Risk: {endpoints['risk']}", file=sys.stderr)
        return 1

    # Load churn analysis query
    query_file = Path(__file__).parent / "churn-analysis-federated.sparql"
    if not query_file.exists():
        print(f"Error: Query file not found: {query_file}", file=sys.stderr)
        return 1

    with open(query_file, "r") as f:
        sparql_query = f.read()

    # Execute query
    print("\nExecuting churn risk analysis query...", file=sys.stderr)
    try:
        results = client.execute_query(sparql_query)
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        return 1

    # Display results
    result_count = len(results)
    exec_time = client.last_execution_time or 0

    print(f"\n{result_count} high-risk customers found ({exec_time:.2f}s)", file=sys.stderr)
    print("=" * 100, file=sys.stderr)

    if result_count == 0:
        print("No high-risk customers found in the last 30 days.", file=sys.stderr)
        return 0

    # Format output
    if args.format == "json":
        import json
        print(json.dumps(results, indent=2))
    else:
        # Table format
        print(client.format_results(results, pretty=True))

    # Summary statistics
    if result_count > 0:
        risk_scores = [float(r.get("riskScore", 0)) for r in results]
        avg_risk = sum(risk_scores) / len(risk_scores)

        print("\n" + "=" * 100, file=sys.stderr)
        print(f"Summary Statistics:", file=sys.stderr)
        print(f"  Total High-Risk Customers: {result_count}", file=sys.stderr)
        print(f"  Average Risk Score: {avg_risk:.3f}", file=sys.stderr)
        print(f"  Max Risk Score: {max(risk_scores):.3f}", file=sys.stderr)
        print(f"  Min Risk Score: {min(risk_scores):.3f}", file=sys.stderr)

        # Count by recommended action
        actions = {}
        for result in results:
            action = result.get("recommendedAction", "UNKNOWN")
            actions[action] = actions.get(action, 0) + 1

        print(f"\n  Recommended Actions:", file=sys.stderr)
        for action, count in sorted(actions.items()):
            print(f"    {action}: {count} customers", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
