import requests
from rdflib import Graph


class RdfWriter:
    """Write RDF triples to Jena TDB2 and Iceberg"""

    def __init__(self, jena_endpoint_url: str):
        """
        Args:
            jena_endpoint_url: HTTP endpoint for Jena SPARQL (e.g., http://localhost:3030/accounts/sparql)
        """
        self.jena_endpoint = jena_endpoint_url

    def write_to_jena(self, rdf_graph: Graph) -> bool:
        """
        Write RDF triples to Jena TDB2 via SPARQL Update endpoint.

        Returns:
            True if successful, False otherwise
        """
        # Serialize graph to N-Triples for SPARQL INSERT
        ntriples = rdf_graph.serialize(format='nt')

        # Build SPARQL UPDATE query
        sparql_update = f"""
        INSERT DATA {{
            {ntriples}
        }}
        """

        # POST to Jena update endpoint
        update_endpoint = self.jena_endpoint.replace('/sparql', '/update')

        try:
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
        """
        Write RDF to local file (for testing/audit).

        Args:
            rdf_graph: RDF graph to serialize
            output_path: Path to output file
            format_: Serialization format (turtle, ntriples, xml, etc.)

        Returns:
            True if successful, False otherwise
        """
        try:
            rdf_graph.serialize(destination=output_path, format=format_)
            return True
        except Exception as e:
            print(f"Error writing to file: {e}")
            return False
