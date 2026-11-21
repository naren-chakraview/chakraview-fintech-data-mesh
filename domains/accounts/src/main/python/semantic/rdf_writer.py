from rdflib import Graph

from shared.semantic.validation import assert_conforms


class RdfWriter:
    """Validate and write RDF to a local file.

    There is no runtime write to Jena. The Fuseki service runs read-only (no /update), so RDF reaches its store
    at deploy time, with an offline load into TDB2 (tdb2.tdbloader), from a snapshot that passed these shapes.
    Product data reaches consumers only through the governed boundary (see docs/case-study/fintech-governance/agent-gaps.md).
    """

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
        assert_conforms(rdf_graph, "accounts")  # validate before writing
        try:
            rdf_graph.serialize(destination=output_path, format=format_)
            return True
        except Exception as e:
            print(f"Error writing to file: {e}")
            return False
