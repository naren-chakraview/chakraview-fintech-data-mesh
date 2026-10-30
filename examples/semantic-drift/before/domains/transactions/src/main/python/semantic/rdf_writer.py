"""Write RDF triples to Jena TDB2 and Iceberg for Transactions domain."""

import requests
from rdflib import Graph
from typing import Optional


class RdfWriter:
    """Write RDF triples to persistent storage."""

    def __init__(self, jena_endpoint_url: str = None):
        """Initialize RDF writer.

        Args:
            jena_endpoint_url: Jena Fuseki SPARQL endpoint URL
        """
        self.jena_endpoint = jena_endpoint_url

    def write_to_jena(self, rdf_graph: Graph) -> bool:
        """Write RDF to Jena TDB2 via SPARQL Update endpoint.

        Args:
            rdf_graph: RDF graph to write

        Returns:
            True if successful, False otherwise
        """
        if not self.jena_endpoint:
            return False

        try:
            # Serialize to N-Triples
            ntriples = rdf_graph.serialize(format='nt')

            # Build SPARQL UPDATE query
            sparql_update = f"""
            INSERT DATA {{
                {ntriples}
            }}
            """

            # Update endpoint from query endpoint
            update_endpoint = self.jena_endpoint.replace('/sparql', '/update')

            # POST to Jena SPARQL Update endpoint
            response = requests.post(
                update_endpoint,
                data=sparql_update,
                headers={'Content-Type': 'application/sparql-update'},
                timeout=10
            )

            return response.status_code == 200
        except Exception as e:
            print(f"Error writing to Jena: {e}")
            return False

    def write_to_file(self, rdf_graph: Graph, output_path: str, format_: str = 'turtle') -> bool:
        """Write RDF to file for testing/audit.

        Args:
            rdf_graph: RDF graph to write
            output_path: File path
            format_: RDF format (turtle, nt, xml)

        Returns:
            True if successful, False otherwise
        """
        try:
            rdf_graph.serialize(destination=output_path, format=format_)
            return True
        except Exception as e:
            print(f"Error writing to file: {e}")
            return False
