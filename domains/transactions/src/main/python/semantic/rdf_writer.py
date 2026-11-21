"""Validate RDF for the Transactions domain before it is written to a file.

There is no runtime write to Jena: Fuseki runs read-only, and RDF is loaded offline at deploy time (see the
accounts RdfWriter for the full reasoning).
"""

from rdflib import Graph

from typing import Optional

from shared.semantic.validation import assert_conforms


class RdfWriter:
    """Validate RDF and write it to a file."""

    def __init__(self, jena_endpoint_url: str = None):
        """Initialize RDF writer.

        Args:
            jena_endpoint_url: Jena Fuseki SPARQL endpoint URL
        """
        self.jena_endpoint = jena_endpoint_url

    def write_to_file(self, rdf_graph: Graph, output_path: str, format_: str = 'turtle') -> bool:
        """Write RDF to file for testing/audit.

        Args:
            rdf_graph: RDF graph to write
            output_path: File path
            format_: RDF format (turtle, nt, xml)

        Returns:
            True if successful, False otherwise
        """
        assert_conforms(rdf_graph, "transactions")  # validate before writing
        try:
            rdf_graph.serialize(destination=output_path, format=format_)
            return True
        except Exception as e:
            print(f"Error writing to file: {e}")
            return False
