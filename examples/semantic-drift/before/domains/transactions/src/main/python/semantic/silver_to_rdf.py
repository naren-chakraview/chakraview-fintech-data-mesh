"""Transform Transactions Silver tables to semantic RDF triples.

Transforms:
- Payment records → Transaction RDF triples
- Counterparty records → Counterparty RDF triples
- Links transactions to customer IRIs from Accounts domain (cross-domain)
"""

import pandas as pd
from rdflib import Graph, Namespace, Literal, URIRef, RDF
from datetime import datetime


class SilverToRdfTransformer:
    """Transform Transactions Silver tables to RDF triples."""

    def __init__(self, iri_resolver, cross_domain_resolver, shared_ontology_path: str):
        """Initialize transformer.

        Args:
            iri_resolver: IriResolver for transaction/counterparty IRIs
            cross_domain_resolver: CrossDomainResolver for customer IRIs
            shared_ontology_path: Path to shared-ontology.ttl
        """
        self.iri_resolver = iri_resolver
        self.cross_domain_resolver = cross_domain_resolver
        self.g = Graph()
        self.g.parse(shared_ontology_path, format='turtle')
        self.FINTECH = Namespace('https://chakracommerce.com/ontology/fintech/')

    def transform_transactions_to_rdf(self, transactions_df: pd.DataFrame) -> Graph:
        """Transform Silver transaction table to RDF triples.

        Args:
            transactions_df: DataFrame with columns:
                - transaction_id: Transaction identifier
                - customer_email: Customer email (for IRI lookup)
                - customer_kyc_id: Customer KYC ID (for IRI lookup)
                - counterparty_id: Counterparty identifier
                - amount: Transaction amount
                - status: Transaction status (executed, failed, pending)
                - transaction_date: When transaction occurred

        Returns:
            RDF graph with Transaction triples and cross-domain Customer links
        """
        for _, row in transactions_df.iterrows():
            # Mint transaction IRI
            txn_iri = URIRef(self.iri_resolver.mint_transaction_iri(row['transaction_id']))

            # Add type declaration (standard RDF)
            self.g.add((txn_iri, RDF.type, self.FINTECH.Transaction))

            # Add transaction properties
            self.g.add((txn_iri, self.FINTECH.transactionId,
                       Literal(row['transaction_id'])))
            self.g.add((txn_iri, self.FINTECH.transactionAmount,
                       Literal(float(row['amount']), datatype=self.FINTECH.decimal)))
            self.g.add((txn_iri, self.FINTECH.transactionStatus,
                       Literal(row['status'])))

            # Add date if present
            if 'transaction_date' in row and pd.notna(row['transaction_date']):
                self.g.add((txn_iri, self.FINTECH.transactionDate,
                           Literal(row['transaction_date'])))

            # Link to customer (cross-domain)
            customer_iri = URIRef(
                self.cross_domain_resolver.resolve_customer_iri(
                    row['customer_email'],
                    row['customer_kyc_id']
                )
            )
            self.g.add((txn_iri, self.FINTECH.transactionDebtor, customer_iri))

            # Link to counterparty
            counterparty_iri = URIRef(
                self.iri_resolver.mint_counterparty_iri(row['counterparty_id'])
            )
            self.g.add((txn_iri, self.FINTECH.transactionCreditor, counterparty_iri))

            # Add metadata
            self.g.add((txn_iri, self.FINTECH.sourceSystem,
                       Literal('transactions')))
            self.g.add((txn_iri, self.FINTECH.sourceIngestionTime,
                       Literal(datetime.now().isoformat())))

        return self.g

    def transform_counterparties_to_rdf(self, counterparties_df: pd.DataFrame) -> Graph:
        """Transform Silver counterparty table to RDF triples.

        Args:
            counterparties_df: DataFrame with columns:
                - counterparty_id: Counterparty identifier
                - name: Counterparty name
                - type: Counterparty type (processor, merchant, bank, etc.)

        Returns:
            RDF graph with Counterparty triples
        """
        for _, row in counterparties_df.iterrows():
            # Mint counterparty IRI
            cp_iri = URIRef(self.iri_resolver.mint_counterparty_iri(row['counterparty_id']))

            # Add type declaration (standard RDF)
            self.g.add((cp_iri, RDF.type, self.FINTECH.Counterparty))

            # Add counterparty properties
            self.g.add((cp_iri, self.FINTECH.counterpartyId,
                       Literal(row['counterparty_id'])))
            self.g.add((cp_iri, self.FINTECH.counterpartyName,
                       Literal(row['name'])))
            self.g.add((cp_iri, self.FINTECH.counterpartyType,
                       Literal(row['type'])))

            # Add metadata
            self.g.add((cp_iri, self.FINTECH.sourceSystem,
                       Literal('transactions')))
            self.g.add((cp_iri, self.FINTECH.sourceIngestionTime,
                       Literal(datetime.now().isoformat())))

        return self.g

    def get_graph(self) -> Graph:
        """Return the RDF graph with all triples."""
        return self.g
