"""Read the SPIFFE ID from a client certificate's URI SAN."""

import urllib.parse

from cryptography import x509
from cryptography.x509.oid import ExtensionOID


class IdentityError(Exception):
    """The certificate does not carry exactly one SPIFFE ID."""


def spiffe_id_from_pem(pem: str) -> str:
    """Return the single spiffe:// URI SAN of a PEM certificate. Accepts a URL-escaped PEM (as nginx forwards it)."""
    if not pem:
        raise IdentityError("no client certificate")
    text = urllib.parse.unquote(pem)
    try:
        certificate = x509.load_pem_x509_certificate(text.encode())
    except ValueError as exc:
        raise IdentityError("client certificate is not valid PEM") from exc

    try:
        san = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    except x509.ExtensionNotFound as exc:
        raise IdentityError("client certificate has no SAN") from exc

    ids = [uri for uri in san.get_values_for_type(x509.UniformResourceIdentifier)
           if uri.startswith("spiffe://")]
    if len(ids) != 1:
        raise IdentityError(f"expected exactly one SPIFFE ID, found {len(ids)}")
    return ids[0]
