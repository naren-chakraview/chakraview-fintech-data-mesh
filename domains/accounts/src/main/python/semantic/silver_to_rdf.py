import pandas as pd
from rdflib import Graph, Namespace, Literal, URIRef
from datetime import datetime


class SilverToRdfTransformer:
    """Transform Accounts Silver tables to RDF triples"""

    def __init__(self, iri_resolver, shared_ontology_path: str):
        """
        Args:
            iri_resolver: IriResolver instance for minting IRIs
            shared_ontology_path: Path to shared-ontology.ttl
        """
        self.iri_resolver = iri_resolver
        self.g = Graph()
        self.g.parse(shared_ontology_path, format='turtle')
        self.FINTECH = Namespace("https://chakracommerce.com/ontology/fintech/")

    def transform_customers_to_rdf(self, customers_df: pd.DataFrame) -> Graph:
        """
        Transform customers Silver table to RDF.
        Generates fintech:Customer triples with properties.
        """
        for _, row in customers_df.iterrows():
            # Mint IRI for customer
            iri = self.iri_resolver.mint_customer_iri(row['email'], row['kyc_id'])
            iri_ref = URIRef(iri)

            # Add Customer properties
            self.g.add((iri_ref, self.FINTECH.customerName, Literal(row['name'])))
            self.g.add((iri_ref, self.FINTECH.customerEmail, Literal(row['email'].lower())))
            self.g.add((iri_ref, self.FINTECH.customerStatus, Literal(row['status'])))
            self.g.add((iri_ref, self.FINTECH.sourceSystem, Literal('accounts')))
            self.g.add((iri_ref, self.FINTECH.sourceIngestionTime,
                       Literal(datetime.now().isoformat())))

        return self.g

    def transform_accounts_to_rdf(self, accounts_df: pd.DataFrame,
                                 customers_df: pd.DataFrame) -> Graph:
        """
        Transform accounts Silver table to RDF.
        Generates fintech:Account triples and links to Customer IRIs.
        """
        # Build customer IRI lookup
        customer_iris = {}
        for _, cust in customers_df.iterrows():
            key = (cust['email'].lower().strip(), cust['kyc_id'].lower().strip())
            iri = self.iri_resolver.mint_customer_iri(cust['email'], cust['kyc_id'])
            customer_iris[key] = iri

        # Transform accounts
        for _, row in accounts_df.iterrows():
            # Mint IRI for account
            account_iri = URIRef(self.iri_resolver.mint_account_iri(row['account_id']))

            # Look up customer IRI
            cust_key = (row['customer_email'].lower().strip(), row['customer_kyc_id'].lower().strip())
            customer_iri = URIRef(customer_iris.get(cust_key))

            # Add Account properties
            self.g.add((account_iri, self.FINTECH.accountId, Literal(row['account_id'])))
            self.g.add((account_iri, self.FINTECH.accountBalance,
                       Literal(float(row['balance']), datatype=self.FINTECH.decimal)))
            self.g.add((account_iri, self.FINTECH.accountStatus, Literal(row['status'])))
            self.g.add((account_iri, self.FINTECH.accountType, Literal(row['account_type'])))
            self.g.add((account_iri, self.FINTECH.accountOwner, customer_iri))
            self.g.add((account_iri, self.FINTECH.sourceSystem, Literal('accounts')))
            self.g.add((account_iri, self.FINTECH.sourceIngestionTime,
                       Literal(datetime.now().isoformat())))

        return self.g

    def get_graph(self) -> Graph:
        """Return the RDF graph with all triples"""
        return self.g
