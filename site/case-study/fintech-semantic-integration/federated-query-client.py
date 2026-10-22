#!/usr/bin/env python3
"""
Federated SPARQL Query Client for fintech semantic mesh.

Executes SPARQL queries across multiple domain endpoints (Accounts, Transactions, Risk/Compliance)
using SERVICE {} federation syntax.
"""

import json
import time
from typing import Dict, List, Optional, Any
import requests
from urllib.parse import quote


class FederatedQueryClient:
    """Client for executing federated SPARQL queries across domain endpoints."""

    def __init__(self, domain_endpoints: Dict[str, str], timeout: int = 30):
        """
        Initialize federated query client.

        Args:
            domain_endpoints: Dictionary mapping domain names to SPARQL endpoint URLs.
                Example: {
                    "accounts": "http://localhost:3030/accounts/sparql",
                    "transactions": "http://localhost:3031/transactions/sparql",
                    "risk": "http://localhost:3032/risk_compliance/sparql"
                }
            timeout: Request timeout in seconds (default: 30)
        """
        self.endpoints = domain_endpoints
        self.timeout = timeout
        self.last_execution_time = None

    def execute_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """
        Execute federated SPARQL query.

        Args:
            sparql_query: SPARQL 1.1 query string with SERVICE {} clauses

        Returns:
            List of result dictionaries from query execution

        Raises:
            requests.RequestException: If any domain endpoint is unreachable
            json.JSONDecodeError: If endpoint returns invalid JSON
        """
        start_time = time.time()

        # For federated queries, we need to send to a federation-aware endpoint
        # In this case, we query through one of the domain endpoints that supports federation
        # Typically the "accounts" endpoint serves as the federation hub
        federation_endpoint = self.endpoints.get("accounts")

        if not federation_endpoint:
            raise ValueError("No 'accounts' endpoint configured for federation hub")

        # Prepare SPARQL query with resolved endpoint URLs
        query_with_endpoints = self._resolve_service_urls(sparql_query)

        # Execute query via HTTP GET/POST
        try:
            response = requests.get(
                federation_endpoint,
                params={"query": query_with_endpoints},
                headers={"Accept": "application/sparql-results+json"},
                timeout=self.timeout
            )
            response.raise_for_status()

            results_json = response.json()
            results = results_json.get("results", {}).get("bindings", [])

            # Convert SPARQL result format to user-friendly format
            results = self._parse_results(results)

            self.last_execution_time = time.time() - start_time
            return results

        except requests.exceptions.Timeout:
            raise TimeoutError(f"Query execution exceeded {self.timeout}s timeout")
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Cannot connect to SPARQL endpoint: {federation_endpoint}") from e

    def _resolve_service_urls(self, sparql_query: str) -> str:
        """
        Replace domain placeholders in SERVICE {} clauses with actual endpoint URLs.

        Supports patterns like:
        - SERVICE <http://accounts-domain/sparql> { ... }
        - SERVICE <http://transactions-domain/sparql> { ... }
        - SERVICE <http://risk-domain/sparql> { ... }
        """
        query = sparql_query

        # Replace domain placeholders with actual endpoints
        replacements = {
            "http://accounts-domain/sparql": self.endpoints.get("accounts", ""),
            "http://transactions-domain/sparql": self.endpoints.get("transactions", ""),
            "http://risk-domain/sparql": self.endpoints.get("risk", ""),
            "http://accounts:3030/accounts/sparql": self.endpoints.get("accounts", ""),
            "http://transactions:3031/transactions/sparql": self.endpoints.get("transactions", ""),
            "http://risk:3032/risk_compliance/sparql": self.endpoints.get("risk", ""),
        }

        for placeholder, endpoint in replacements.items():
            if placeholder in query and endpoint:
                query = query.replace(placeholder, endpoint)

        return query

    def _parse_results(self, raw_results: List[Dict]) -> List[Dict[str, str]]:
        """
        Convert SPARQL JSON result format to user-friendly format.

        SPARQL format: {"var": {"type": "literal", "value": "..."}}
        User format: {"var": "..."}
        """
        parsed = []
        for binding in raw_results:
            row = {}
            for var_name, var_binding in binding.items():
                if isinstance(var_binding, dict) and "value" in var_binding:
                    row[var_name] = var_binding["value"]
                else:
                    row[var_name] = str(var_binding)
            parsed.append(row)
        return parsed

    def format_results(self, results: List[Dict[str, str]], pretty: bool = True) -> str:
        """
        Format query results for display.

        Args:
            results: List of result dictionaries
            pretty: If True, format as readable table; if False, return JSON

        Returns:
            Formatted string representation of results
        """
        if not results:
            return "No results found."

        if not pretty:
            return json.dumps(results, indent=2)

        # Format as aligned table
        lines = []

        # Get column names from first result
        columns = list(results[0].keys())
        col_widths = {col: len(col) for col in columns}

        # Calculate column widths
        for result in results:
            for col in columns:
                col_widths[col] = max(col_widths[col], len(str(result.get(col, ""))))

        # Header
        header = " | ".join(col.ljust(col_widths[col]) for col in columns)
        separator = "-+-".join("-" * col_widths[col] for col in columns)
        lines.append(header)
        lines.append(separator)

        # Rows
        for result in results:
            row = " | ".join(str(result.get(col, "")).ljust(col_widths[col]) for col in columns)
            lines.append(row)

        return "\n".join(lines)

    def check_endpoints(self) -> Dict[str, bool]:
        """
        Check availability of all configured endpoints.

        Returns:
            Dictionary mapping domain names to availability status
        """
        status = {}
        for domain, endpoint in self.endpoints.items():
            try:
                response = requests.get(endpoint, timeout=5)
                status[domain] = response.status_code == 200
            except:
                status[domain] = False
        return status


def main():
    """Example usage of FederatedQueryClient."""
    # Configure endpoints
    endpoints = {
        "accounts": "http://localhost:3030/accounts/sparql",
        "transactions": "http://localhost:3031/transactions/sparql",
        "risk": "http://localhost:3032/risk_compliance/sparql"
    }

    # Create client
    client = FederatedQueryClient(endpoints)

    # Check endpoints
    print("Checking endpoint availability...")
    status = client.check_endpoints()
    for domain, available in status.items():
        print(f"  {domain}: {'✓' if available else '✗'}")

    # Simple test query
    test_query = """
    PREFIX fintech: <https://chakracommerce.com/ontology/fintech/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

    SELECT (COUNT(?customer) as ?count)
    WHERE {
      SERVICE <http://accounts-domain/sparql> {
        ?customer a fintech:Customer
      }
    }
    """

    print("\nExecuting test query...")
    try:
        results = client.execute_query(test_query)
        print(client.format_results(results))
        print(f"Execution time: {client.last_execution_time:.2f}s")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
