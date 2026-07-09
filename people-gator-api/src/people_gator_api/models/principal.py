import logging
import re
import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum as SAEnum, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.models.enums import AnnotationType, PrincipalType, RegistrySource
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)

# Conventional agent slug: <category>:<name>  e.g. "system:kramerius-ingest"
_AGENT_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")


class Principal(Base):
    """Base identity record for any actor that can modify the system.

    Uses SQLAlchemy joined-table inheritance — type-specific fields live in
    the ``user`` or ``service_agent`` tables.
    """

    __tablename__ = "principal"

    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    principal_type: Mapped[PrincipalType] = mapped_column(
        SAEnum(PrincipalType, name="principal_type_enum"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __mapper_args__ = {
        "polymorphic_on": "principal_type",
        "polymorphic_identity": None,
    }

    # -------------------------------------------------------------------------
    # Hybrid predicates
    # -------------------------------------------------------------------------

    @hybrid_property
    def is_user(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.principal_type == PrincipalType.user

    @is_user.expression
    @classmethod
    def is_user(cls) -> sa.ColumnElement[bool]:
        return cls.principal_type == PrincipalType.user.value

    @hybrid_property
    def is_service_agent(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.principal_type == PrincipalType.service_agent

    @is_service_agent.expression
    @classmethod
    def is_service_agent(cls) -> sa.ColumnElement[bool]:
        return cls.principal_type == PrincipalType.service_agent.value

    @hybrid_property
    def is_model_agent(self) -> bool:  # pyright: ignore[reportRedeclaration]
        return self.principal_type == PrincipalType.model_agent

    @is_model_agent.expression
    @classmethod
    def is_model_agent(cls) -> sa.ColumnElement[bool]:
        return cls.principal_type == PrincipalType.model_agent.value

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> "Principal | None":
        result = await session.scalars(
            select(cls).where(cls.principal_id == principal_id)
        )
        return result.one_or_none()

    # -------------------------------------------------------------------------
    # Instance-level operations
    # -------------------------------------------------------------------------

    async def deactivate(self, session: AsyncSession) -> None:
        self.is_active = False
        session.add(self)
        logger.info(
            "Deactivated principal",
            extra={
                "principal_id": str(self.principal_id),
                "principal_type": self.principal_type.value,
            },
        )


class User(Principal):
    """A human principal authenticated via an external OIDC provider.

    The stable identity key is ``(external_subject, external_issuer)`` — the
    ``sub`` and ``iss`` claims from the OIDC ID token.  Users are created or
    updated on first successful token verification.
    """

    __tablename__ = "user"
    # OIDC sub — stable, provider-scoped user identifier.
    external_subject: Mapped[str] = mapped_column(String, nullable=False)
    # OIDC iss — identifies the identity provider.
    external_issuer: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "external_subject",
            "external_issuer",
            name="uq_user_external_identity",
        ),
    )

    __mapper_args__ = {
        "polymorphic_identity": PrincipalType.user
    }

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_by_external_identity(
        cls,
        session: AsyncSession,
        external_subject: str,
        external_issuer: str,
    ) -> "User | None":
        result = await session.scalars(
            select(cls).where(
                cls.external_subject == external_subject,
                cls.external_issuer == external_issuer,
            )
        )
        return result.one_or_none()

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        external_subject: str,
        external_issuer: str,
        display_name: str,
        email: str | None = None,
    ) -> tuple["User", bool]:
        """Return ``(user, created)`` — create if the OIDC identity is new.

        ``display_name`` and ``email`` are refreshed on every call so the
        local record stays in sync with the IdP's current claims.
        """
        user = await cls.get_by_external_identity(
            session, external_subject, external_issuer
        )
        if user is not None:
            user.display_name = display_name
            user.email = email
            session.add(user)
            logger.debug(
                "Refreshed user from OIDC claims",
                extra={
                    "principal_id": str(user.principal_id),
                    "external_issuer": external_issuer,
                },
            )
            return user, False

        user = cls(
            principal_id=new_uuid6(),
            principal_type=PrincipalType.user,
            display_name=display_name,
            is_active=True,
            external_subject=external_subject,
            external_issuer=external_issuer,
            email=email,
        )
        session.add(user)
        logger.info(
            "Created user from OIDC identity",
            extra={
                "principal_id": str(user.principal_id),
                "external_subject": external_subject,
                "external_issuer": external_issuer,
            },
        )
        return user, True


class ServiceAgent(Principal):
    """A named autonomous process that drives ingestion and synchronisation pipelines.

    SERVICE_AGENTs produce AUTHORITY_EVIDENCE and create SOURCE records during
    ingest.  They are identified by a unique ``agent_slug`` following the
    convention ``<category>:<name>``, e.g. ``system:kramerius-ingest``.
    ML model agents are registered as MODEL_AGENT instead.
    """

    __tablename__ = "service_agent"
    # Convention: "<category>:<name>"  e.g. "system:kramerius-ingest"
    agent_slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    __mapper_args__ = {"polymorphic_identity": PrincipalType.service_agent}

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_by_slug(
        cls,
        session: AsyncSession,
        agent_slug: str,
    ) -> "ServiceAgent | None":
        result = await session.scalars(
            select(cls).where(cls.agent_slug == agent_slug)
        )
        return result.one_or_none()

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        agent_slug: str,
        display_name: str,
    ) -> tuple["ServiceAgent", bool]:
        """Return ``(agent, created)`` — create if the slug is not registered."""
        if not _AGENT_SLUG_RE.match(agent_slug):
            raise ValueError(
                f"agent_slug must match '<category>:<name>' (lowercase, hyphens allowed), got: {agent_slug!r}"
            )

        agent = await cls.get_by_slug(session, agent_slug)
        if agent is not None:
            return agent, False

        agent = cls(
            principal_id=new_uuid6(),
            principal_type=PrincipalType.service_agent,
            display_name=display_name,
            is_active=True,
            agent_slug=agent_slug,
        )
        session.add(agent)
        logger.info(
            "Registered service agent",
            extra={
                "principal_id": str(agent.principal_id),
                "agent_slug": agent_slug,
            },
        )
        return agent, True


class ModelAgent(Principal):
    """A registered ML model agent principal that produces DERIVED_EVIDENCE.

    Every model that produces EVIDENCE must be pre-registered as a MODEL_AGENT.
    The ``(annotation_type, role, model_slug)`` triple uniquely identifies the
    vector slot this agent populates in the vector store.

    The slot name follows the pattern ``<role>:<model_slug>``, e.g.
    ``face:arcface-r100-v2`` or ``text:multilingual-e5-large-v1``.
    """

    __tablename__ = "model_agent"
    annotation_type: Mapped[AnnotationType] = mapped_column(
        SAEnum(AnnotationType, name="annotation_type_enum"),
        nullable=False,
    )
    # Vector slot role prefix, e.g. "face", "text", "layout", "authority".
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Suffix component of the slot name: <role>:<model_slug>.
    model_slug: Mapped[str] = mapped_column(String, nullable=False)
    # Semantic version of the underlying model artifact for staleness detection.
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    registry_source: Mapped[RegistrySource] = mapped_column(
        SAEnum(RegistrySource, name="registry_source_enum"),
        nullable=False,
    )
    # Fully-qualified URI for this model version in its registry.
    registry_uri: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "annotation_type", "role", "model_slug",
            name="uq_model_agent_annotation_role_slug",
        ),
        sa.Index("ix_model_agent_annotation_type", "annotation_type"),
    )

    __mapper_args__ = {"polymorphic_identity": PrincipalType.model_agent}

    @property
    def slot_name(self) -> str:
        """Full vector slot name as stored in the vector store."""
        return f"{self.role}:{self.model_slug}"

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get_active_for_annotation_type(
        cls,
        session: AsyncSession,
        annotation_type: AnnotationType,
    ) -> list["ModelAgent"]:
        result = await session.execute(
            select(cls).where(
                cls.annotation_type == annotation_type,
                cls.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def get_by_slot(
        cls,
        session: AsyncSession,
        annotation_type: AnnotationType,
        role: str,
        model_slug: str,
    ) -> "ModelAgent | None":
        result = await session.scalars(
            select(cls).where(
                cls.annotation_type == annotation_type,
                cls.role == role,
                cls.model_slug == model_slug,
            )
        )
        return result.one_or_none()
