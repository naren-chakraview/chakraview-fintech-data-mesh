"""Transform Risk/Compliance Silver tables to semantic RDF triples.

Transforms:
- Risk profile records → RiskProfile RDF triples
- Links risk profiles to customer IRIs from Accounts domain (cross-domain)
"""

import pandas as pd
from rdflib import Graph, Namespace, Literal, URIRef, RDF, XSD
from datetime import datetime


class SilverToRdfTransformer:
    """Transform Risk/Compliance Silver tables to RDF triples."""

    def __init__(self, iri_resolver, cross_domain_resolver, shared_ontology_path: str):
        """Initialize transformer.

        Args:
            iri_resolver: IriResolver for risk profile IRIs
            cross_domain_resolver: CrossDomainResolver for customer IRIs
            shared_ontology_path: Path to shared-ontology.ttl
        """
        self.iri_resolver = iri_resolver
        self.cross_domain_resolver = cross_domain_resolver
        self.g = Graph()
        self.g.parse(shared_ontology_path, format='turtle')
        self.FINTECH = Namespace('https://chakracommerce.com/ontology/fintech/')

    def transform_risk_profiles_to_rdf(self, risk_profiles_df: pd.DataFrame) -> Graph:
        """Transform Silver risk profile table to RDF triples.

        Args:
            risk_profiles_df: DataFrame with columns:
                - risk_id: Risk profile identifier
                - customer_email: Customer email (for IRI lookup)
                - customer_kyc_id: Customer KYC ID (for IRI lookup)
                - risk_score: Risk score (0-1, float)
                - risk_level: Risk level (LOW, MEDIUM, HIGH, CRITICAL)
                - compliance_status: Compliance status (COMPLIANT, UNDER_REVIEW, NON_COMPLIANT, SUSPENDED)
                - kyc_status: KYC status (NOT_STARTED, IN_PROGRESS, VERIFIED, REJECTED, EXPIRED)
                - fraud_flags_count: Number of fraud flags (int)
                - last_review_date: Last review date (datetime)
                - next_review_date: Next review date (datetime)
                - review_notes: Review notes (optional, string)

        Returns:
            RDF graph with RiskProfile triples and cross-domain Customer links

        Raises:
            ValueError: If customer reference not found
        """
        for _, row in risk_profiles_df.iterrows():
            # Mint risk profile IRI
            risk_iri = URIRef(self.iri_resolver.mint_risk_profile_iri(row['risk_id']))

            # Add type declaration (standard RDF)
            self.g.add((risk_iri, RDF.type, self.FINTECH.RiskProfile))

            # Add risk profile properties
            self.g.add((risk_iri, self.FINTECH.riskProfileId,
                       Literal(row['risk_id'])))
            self.g.add((risk_iri, self.FINTECH.riskScore,
                       Literal(float(row['risk_score']), datatype=XSD.decimal)))
            self.g.add((risk_iri, self.FINTECH.riskLevel,
                       Literal(row['risk_level'])))
            self.g.add((risk_iri, self.FINTECH.complianceStatus,
                       Literal(row['compliance_status'])))
            self.g.add((risk_iri, self.FINTECH.kycStatus,
                       Literal(row['kyc_status'])))
            self.g.add((risk_iri, self.FINTECH.fraudFlagsCount,
                       Literal(int(row['fraud_flags_count']), datatype=XSD.integer)))

            # Add dates if present
            if 'last_review_date' in row and pd.notna(row['last_review_date']):
                self.g.add((risk_iri, self.FINTECH.lastReviewDate,
                           Literal(pd.Timestamp(row['last_review_date']).isoformat(),
                                  datatype=XSD.dateTime)))

            if 'next_review_date' in row and pd.notna(row['next_review_date']):
                self.g.add((risk_iri, self.FINTECH.nextReviewDate,
                           Literal(pd.Timestamp(row['next_review_date']).isoformat(),
                                  datatype=XSD.dateTime)))

            # Add review notes if present
            if 'review_notes' in row and pd.notna(row['review_notes']):
                self.g.add((risk_iri, self.FINTECH.reviewNotes,
                           Literal(row['review_notes'])))

            # Link to customer (cross-domain)
            try:
                customer_iri = URIRef(
                    self.cross_domain_resolver.resolve_customer_iri(
                        row['customer_email'],
                        row['customer_kyc_id']
                    )
                )
                self.g.add((risk_iri, self.FINTECH.forCustomer, customer_iri))
            except Exception as e:
                raise ValueError(
                    f"Failed to resolve customer IRI for risk_id={row['risk_id']}, "
                    f"email={row['customer_email']}, kyc_id={row['customer_kyc_id']}: {str(e)}"
                )

            # Add metadata
            self.g.add((risk_iri, self.FINTECH.sourceSystem,
                       Literal('risk_compliance')))
            self.g.add((risk_iri, self.FINTECH.sourceIngestionTime,
                       Literal(datetime.now().isoformat())))

        return self.g

    def get_graph(self) -> Graph:
        """Return the RDF graph with all triples."""
        return self.g
