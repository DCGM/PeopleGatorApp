"""Pydantic schemas for SOURCE_SCHEMA.resolver_config JSONB payloads.

Each class corresponds to a ResolverType value and defines the expected
structure of the ``resolver_config`` column for source schemas of that type.

Template variables (e.g. ``{provider_id}``, ``{page}``) embedded in string
fields are interpolated from ``SOURCE.provider_id`` and ``RECORD.source_path``
values at resolution time.

See: docs/01-product-spec.md §5.1
"""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Resolver protocol — common interface for all resolver config models
# ---------------------------------------------------------------------------


class SupportsResolve(Protocol):
    """Structural interface implemented by all resolver config models."""

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        """Return the fully resolved path or URL for this source."""
        ...


# ---------------------------------------------------------------------------
# Per resolver-type config schemas
# ---------------------------------------------------------------------------


class LocalFilesystemResolverConfig(BaseModel):
    """Config for ResolverType.local_filesystem sources.

    Example::

        LocalFilesystemResolverConfig(
            base_path="/data/scans",
            path_template="{provider_id}/{page}.tif",
        )
    """

    base_path: str
    path_template: str

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        context: dict[str, object] = {
            "provider": provider,
            "provider_id": provider_id,
            **(source_path or {}),
        }
        return str(Path(self.base_path) / self.path_template.format_map(context))


class S3ResolverConfig(BaseModel):
    """Config for ResolverType.s3 sources.

    Example::

        S3ResolverConfig(
            bucket="scan-archive",
            key_template="{provider}/{provider_id}.jpg",
        )
    """

    bucket: str
    key_template: str
    region: str | None = None
    endpoint_url: str | None = None

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        context: dict[str, object] = {
            "provider": provider,
            "provider_id": provider_id,
            **(source_path or {}),
        }
        key = self.key_template.format_map(context)
        return f"s3://{self.bucket}/{key}"


class IIIFResolverConfig(BaseModel):
    """Config for ResolverType.iiif sources.

    Example::

        IIIFResolverConfig(
            base_url="https://kramerius.example.org/iiif/3",
            manifest_template="{provider_id}/manifest",
        )
    """

    base_url: str
    manifest_template: str

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        context: dict[str, object] = {
            "provider": provider,
            "provider_id": provider_id,
            **(source_path or {}),
        }
        manifest = self.manifest_template.format_map(context)
        return f"{self.base_url.rstrip('/')}/{manifest}"


class HTTPResolverConfig(BaseModel):
    """Config for ResolverType.http sources (documents and authority systems).

    Examples::

        # CDN scan archive
        HTTPResolverConfig(
            base_url="https://cdn.example.org/scans",
            path_template="{provider_id}",
        )

        # Wikidata authority
        HTTPResolverConfig(
            base_url="https://www.wikidata.org/wiki",
            path_template="{provider_id}",
        )

        # NKCR authority
        HTTPResolverConfig(
            base_url="https://aleph.nkp.cz/F",
            path_template="?func=find-c&ccl_term=sys={provider_id}",
        )
    """

    base_url: str
    path_template: str

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        context: dict[str, object] = {
            "provider": provider,
            "provider_id": provider_id,
            **(source_path or {}),
        }
        path = self.path_template.format_map(context)
        if path.startswith(("?", "#")):
            return f"{self.base_url}{path}"
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


class SparqlResolverConfig(BaseModel):
    """Config for ResolverType.sparql sources (RDF/SPARQL authority endpoints).

    Used for authority sources queried via SPARQL, such as Wikidata or local
    RDF triple stores.  ``query_template`` is a SPARQL SELECT query string
    with ``{provider_id}`` placeholder interpolated from ``SOURCE.provider_id``.

    Example::

        SparqlResolverConfig(
            endpoint_url="https://query.wikidata.org/sparql",
            query_template="SELECT ?item WHERE { ?item wdt:P31 wd:{provider_id} }",
        )
    """

    endpoint_url: str
    query_template: str

    def resolve(
        self,
        provider: str,
        provider_id: str,
        source_path: dict[str, object] | None = None,
    ) -> str:
        context: dict[str, object] = {
            "provider": provider,
            "provider_id": provider_id,
            **(source_path or {}),
        }
        return self.query_template.format_map(context)


# ---------------------------------------------------------------------------
# Union type for use in typed resolution helpers
# ---------------------------------------------------------------------------

ResolverConfig = (
    LocalFilesystemResolverConfig
    | S3ResolverConfig
    | IIIFResolverConfig
    | HTTPResolverConfig
    | SparqlResolverConfig
)
