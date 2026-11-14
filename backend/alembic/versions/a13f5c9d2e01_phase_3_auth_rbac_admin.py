"""Phase 3 authentication, RBAC and administration schema.

Revision ID: a13f5c9d2e01
Revises: 7c0f74402c2b
Create Date: 2026-11-12 09:00:00.000000

Additive only: refresh-token state, durable lockout counters, versioned response
policies and sensor key metadata. The Phase 2 audit guard and least-privilege
grants are re-applied so the new table is reachable by the runtime role and
still append-only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a13f5c9d2e01"
down_revision: str | None = "7c0f74402c2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _app_role() -> str:
    role = op.get_context().config.get_main_option("app_db_role", "slotwise_app")
    if not _ROLE_NAME.fullmatch(role):
        raise ValueError("DATABASE_APP_ROLE contains unsafe characters")
    return role


def _grant_application_role() -> None:
    role = _app_role()
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT USAGE ON SCHEMA public TO {role};
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role};
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role};
                GRANT SELECT ON alembic_version TO {role};
                REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {role};
                REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM {role};
            END IF;
        END $$;
        """  # noqa: S608 - role is validated against a strict identifier pattern
    )


def _create_policy_guard() -> None:
    """Policy versions are append-only; only ``enabled`` may change.

    The check runs in the database so a direct SQL client cannot rewrite the
    conditions of a policy that has already been used to justify a response.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION response_policies_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'response policy versions are append-only'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF EXISTS (SELECT 1 FROM response_policies WHERE supersedes_id = OLD.id) THEN
                RAISE EXCEPTION 'superseded response policy version is immutable'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF NEW.name IS DISTINCT FROM OLD.name
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id
               OR NEW.action_type IS DISTINCT FROM OLD.action_type
               OR NEW.conditions IS DISTINCT FROM OLD.conditions
               OR NEW.requires_approval IS DISTINCT FROM OLD.requires_approval
               OR NEW.created_by IS DISTINCT FROM OLD.created_by
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'response policy content is immutable; create a new version'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER response_policies_no_update BEFORE UPDATE ON response_policies "
        "FOR EACH ROW EXECUTE FUNCTION response_policies_immutable()"
    )
    op.execute(
        "CREATE TRIGGER response_policies_no_delete BEFORE DELETE ON response_policies "
        "FOR EACH ROW EXECUTE FUNCTION response_policies_immutable()"
    )


def upgrade() -> None:
    # -- users: durable lockout and password lifecycle ----------------------
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_check_constraint(
        "failed_login_count_non_negative", "users", "failed_login_count >= 0"
    )

    # -- refresh tokens ------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.UUID(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_refresh_tokens_token_hash_sha256")
        ),
        sa.CheckConstraint(
            "expires_at > issued_at", name=op.f("ck_refresh_tokens_expires_after_issue")
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL OR used_at <= revoked_at",
            name=op.f("ck_refresh_tokens_used_before_revoked"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index(
        "ix_refresh_tokens_user_family", "refresh_tokens", ["user_id", "family_id"], unique=False
    )
    op.create_index("ux_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    # -- response policy versioning -----------------------------------------
    op.drop_constraint("uq_response_policies_name", "response_policies", type_="unique")
    op.add_column(
        "response_policies",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("response_policies", sa.Column("supersedes_id", sa.UUID(), nullable=True))
    op.create_check_constraint("version_positive", "response_policies", "version > 0")
    op.create_foreign_key(
        op.f("fk_response_policies_supersedes_id_response_policies"),
        "response_policies",
        "response_policies",
        ["supersedes_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_response_policies_name_version", "response_policies", ["name", "version"]
    )
    op.create_index(
        "ix_response_policies_name_version",
        "response_policies",
        ["name", "version"],
        unique=False,
    )
    _create_policy_guard()

    # -- sensors: lookup prefix, rotation and revocation --------------------
    op.add_column("sensors", sa.Column("credential_prefix", sa.String(length=32), nullable=True))
    op.add_column(
        "sensors", sa.Column("credential_rotated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("sensors", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE sensors SET revoked_at = now() WHERE status = 'REVOKED' AND revoked_at IS NULL"
    )
    op.create_check_constraint(
        "credential_prefix_format",
        "sensors",
        "credential_prefix IS NULL OR credential_prefix ~ '^[a-z0-9]{8,32}$'",
    )
    op.create_check_constraint(
        "revoked_requires_timestamp",
        "sensors",
        "status <> 'REVOKED' OR revoked_at IS NOT NULL",
    )
    op.create_index(
        "ux_sensors_credential_prefix",
        "sensors",
        ["credential_prefix"],
        unique=True,
        postgresql_where=sa.text("credential_prefix IS NOT NULL"),
    )

    _grant_application_role()


def downgrade() -> None:
    op.drop_index(op.f("ux_sensors_credential_prefix"), table_name="sensors")
    # Use op.f() to prevent naming convention from being re-applied
    op.drop_constraint(op.f("ck_sensors_revoked_requires_timestamp"), "sensors", type_="check")
    op.drop_constraint(op.f("ck_sensors_credential_prefix_format"), "sensors", type_="check")
    op.drop_column("sensors", "revoked_at")
    op.drop_column("sensors", "credential_rotated_at")
    op.drop_column("sensors", "credential_prefix")

    op.execute("DROP TRIGGER IF EXISTS response_policies_no_delete ON response_policies")
    op.execute("DROP TRIGGER IF EXISTS response_policies_no_update ON response_policies")
    op.execute("DROP FUNCTION IF EXISTS response_policies_immutable()")
    op.drop_index(op.f("ix_response_policies_name_version"), table_name="response_policies")
    op.drop_constraint(
        op.f("uq_response_policies_name_version"), "response_policies", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_response_policies_supersedes_id_response_policies"),
        "response_policies",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_response_policies_version_positive"), "response_policies", type_="check"
    )
    op.drop_column("response_policies", "supersedes_id")
    op.drop_column("response_policies", "version")
    op.create_unique_constraint(op.f("uq_response_policies_name"), "response_policies", ["name"])

    op.drop_index(op.f("ux_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_family"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_constraint(op.f("ck_users_failed_login_count_non_negative"), "users", type_="check")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
