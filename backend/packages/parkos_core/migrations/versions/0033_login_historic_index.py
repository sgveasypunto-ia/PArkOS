"""MIGRATION 0033 -- F1.15 REAL DDL composite index for login history pagination.

Pre-flight 2026-09-15 confirmed:
- prod.login exists (migration 0001:511-523, [L-S] SessionBase, 5 business columns).
- prod.usuarios exists (migration 0001:7-50, [V] VersionedBase, bi-temporal).
- prod.login has FK fk_login_uuid_usuario (migration 0001:1247-1255) -- implicit
  index on uuid_usuario already exists. NO composite index on
  (uuid_usuario, timestamp_evento DESC) exists today.
- F1.15 adds the composite index to enable cursor pagination at scale
  (1000+ login rows per user over months -> no sort-on-disk).

This migration ships:
- Op 0: pre-flight DO $$ block asserting required tables exist (login, usuarios).
- Op 1: CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento
  on prod.login (uuid_usuario, timestamp_evento DESC).

Idempotency ensures any future re-run on already-migrated DB is a clean no-op
(CREATE INDEX CONCURRENTLY IF NOT EXISTS pattern).

Part of HU-F1.15 (gap huérfano de auditoría de seguridad, ÚLTIMA HU de Fase 1 Parte I).
Predecessor: F1.14 archived 2026-09-15 (MIGRATION 0032 alert_types siembra).
"""
from alembic import op

revision = "0033_login_historic_index"
down_revision = "0032_seed_alert_types_operativos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """MIGRATION 0033 upgrade: pre-flight DO $$ + Op 1 CREATE INDEX CONCURRENTLY.

    CREATE INDEX CONCURRENTLY cannot run inside a transaction -- alembic
    defaults to transactional DDL; we explicitly opt OUT for this op via
    autocommit_block() (KD-7 F1.6..F1.14 pattern).
    """
    # Op 0 -- pre-flight DO $$ (KD-7 F1.6..F1.14 pattern).
    # Verifies the 2 tables required by F1.15 are present in ``prod``.
    op.execute(
        """
        DO $$
        DECLARE
            _n_login      bigint;
            _n_usuarios   bigint;
        BEGIN
            SELECT count(*) INTO _n_login
                FROM pg_catalog.pg_class
                WHERE relname='login' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_usuarios
                FROM pg_catalog.pg_class
                WHERE relname='usuarios' AND relnamespace='prod'::regnamespace;

            IF _n_login IS NULL OR _n_login = 0 THEN
                RAISE EXCEPTION '0033_preflight_abort: tabla prod.login no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_usuarios IS NULL OR _n_usuarios = 0 THEN
                RAISE EXCEPTION '0033_preflight_abort: tabla prod.usuarios no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            RAISE NOTICE '0033_preflight: 2/2 tablas OK (login, usuarios)';
        END;
        $$;
        """
    )

    # Op 1 -- CREATE INDEX CONCURRENTLY (DEC-LOGIN-06).
    # Avoids table lock during index build (production safety -- F1.2
    # lockout writes from record_login are not blocked).
    # IF NOT EXISTS makes the migration idempotent on re-run.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_login_uuid_usuario_evento
            ON prod.login (uuid_usuario, timestamp_evento DESC);
            """
        )


def downgrade() -> None:
    """Reverse Op 1: DROP INDEX CONCURRENTLY (production safety -- no table lock).

    DROP INDEX CONCURRENTLY cannot run inside a transaction; explicit opt-out
    via autocommit_block().
    """
    with op.get_context().autocommit_block():
        op.execute(
            """
            DROP INDEX CONCURRENTLY IF EXISTS
                idx_login_uuid_usuario_evento;
            """
        )
