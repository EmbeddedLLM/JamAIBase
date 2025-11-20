from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from typing import AsyncGenerator, Callable, Generator

from loguru import logger
from sqlalchemy import Connection, Engine, NullPool, TextClause, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Session, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from owl.configs import CACHE, ENV_CONFIG
from owl.db.models import TEMPLATE_ORG_ID, JamaiSQLModel  # noqa: F401
from owl.utils import uuid7_str

SCHEMA = JamaiSQLModel.metadata.schema


def _create_db_engine(
    db_url: str,
    *,
    connect_args: dict | None = None,
    engine_create_fn: Callable[..., Engine | AsyncEngine] | None = None,
    echo: bool = False,
    dialect: str = "sqlite",
) -> Engine:
    if connect_args is None:
        if dialect == "postgresql":
            connect_args = {}
        else:
            connect_args = {"check_same_thread": False}
    if engine_create_fn is None:
        engine_create_fn = create_engine
    if dialect == "postgresql":
        logger.debug("Using PostgreSQL DB.")
        if "asyncpg" in db_url:
            connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid7_str()}__"
        engine = engine_create_fn(
            db_url,
            connect_args=connect_args,
            poolclass=NullPool,
            echo=echo,
        )
    else:
        raise ValueError(f'Dialect "{dialect}" is not supported.')
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except ImportError:
        logger.warning("Skip sqlalchemy instrumentation.")
    else:
        SQLAlchemyInstrumentor().instrument(
            engine=engine if isinstance(engine, Engine) else engine.sync_engine,
            enable_commenter=True,
            commenter_options={},
        )
    return engine


@lru_cache(maxsize=1)
def create_db_engine() -> Engine:
    engine = _create_db_engine(
        ENV_CONFIG.db_path,
        dialect=ENV_CONFIG.db_dialect,
    )
    return engine


@lru_cache(maxsize=1)
def create_db_engine_async() -> AsyncEngine:
    engine = _create_db_engine(
        ENV_CONFIG.db_path,
        engine_create_fn=create_async_engine,
        dialect=ENV_CONFIG.db_dialect,
    )
    return engine


def yield_session() -> Generator[Session, None, None]:
    with Session(create_db_engine()) as session:
        yield session


async def yield_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(create_db_engine_async(), expire_on_commit=False) as session:
        yield session


# Sync Session context manager
sync_session = contextmanager(yield_session)
# Async Session context manager
async_session = asynccontextmanager(yield_async_session)


@lru_cache(maxsize=10000)
def cached_text(query: str) -> TextClause:
    return text(query)


async def reset_db(*, reset_max_users: int = 3):
    from sqlmodel import func, select

    from owl.db.models import User

    # Only allow DB reset in dev with localhost
    if "@localhost:" not in ENV_CONFIG.db_path:
        raise ValueError("DB reset is only allowed in dev with localhost DB.")

    async with async_session() as session:
        # As a safety measure, reset DB only if it has less than `init_max_users` users
        # Just in case we accidentally tried to nuke a prod DB
        user_table_exists = (
            await session.exec(
                text(
                    (
                        f"SELECT EXISTS ("
                        f"SELECT FROM information_schema.tables WHERE table_schema = '{SCHEMA}' AND table_name = 'User'"
                        ");"
                    )
                )
            )
        ).scalar()
        if user_table_exists:
            user_count = (await session.exec(select(func.count(User.id)))).one()
            if user_count >= reset_max_users:
                logger.info(
                    f"Found {user_count:,d} users, abort database reset (>= {reset_max_users} users)."
                )
                return

        # Delete all tables
        logger.warning(f'Resetting database (dropping schema "{SCHEMA}")...')
        await session.exec(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await session.exec(text(f"CREATE SCHEMA {SCHEMA}"))
        # Reapply default privileges for the new schema OID
        await _grant_auditor_privilege(create_db_engine_async())
        await session.commit()
        stmt = """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name ~ '^proj_.*(_action|_knowledge|_chat)$';
        """
        schemas = [r[0] for r in (await session.exec(text(stmt))).all()]
        logger.warning(f'Dropping Generative Table schemas: "{schemas}"')
        for schema in schemas:
            await session.exec(text(f"DROP SCHEMA {schema} CASCADE"))
        await session.commit()
        conn = await session.connection()
        await conn.run_sync(JamaiSQLModel.metadata.create_all)
        await conn.commit()
        logger.success("All application tables dropped and recreated.")


async def _create_schema(engine: AsyncEngine) -> bool:
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        await conn.commit()
    return False


async def _create_tables(engine: AsyncEngine) -> bool:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(JamaiSQLModel.metadata.create_all)
            await conn.commit()
    except Exception as e:
        logger.exception(f"Failed to create DB tables: {e}")
        if not isinstance(e, OperationalError):
            raise
    return False


async def _create_pg_functions(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        await conn.execute(
            text(f"""
            CREATE OR REPLACE FUNCTION {SCHEMA}.deduct_cost(
                organization_id TEXT,
                cost NUMERIC(21, 12)
            )
            RETURNS {SCHEMA}."Organization" AS $$
            DECLARE
                updated_org {SCHEMA}."Organization"%ROWTYPE;
            BEGIN
                -- Ensure the cost is a positive number to prevent misuse
                IF cost < 0 THEN
                    RAISE EXCEPTION 'Cost must be a non-negative number.';
                END IF;

                UPDATE {SCHEMA}."Organization"
                SET
                    -- Logic for credit_grant column
                    credit_grant = CASE
                        -- If grant is enough to cover the cost, deduct from grant
                        WHEN credit_grant >= cost THEN credit_grant - cost
                        -- Otherwise, the grant is fully used up
                        ELSE 0
                    END,
                    -- Logic for credit column
                    credit = CASE
                        -- If grant is enough, credit is unchanged
                        WHEN credit_grant >= cost THEN credit
                        -- Otherwise, deduct the remainder of the cost from credit
                        ELSE credit - (cost - credit_grant)
                    END
                WHERE id = organization_id
                RETURNING * INTO updated_org; -- Capture the updated row into a variable

                RETURN updated_org;
            END;
            $$ LANGUAGE plpgsql;
            """)
        )
        await conn.execute(
            text(f"""
                CREATE OR REPLACE FUNCTION {SCHEMA}.add_credit_grant(
                    organization_id TEXT,
                    grant_to_add NUMERIC(21, 12)
                )
                RETURNS {SCHEMA}."Organization" AS $$
                DECLARE
                    updated_org {SCHEMA}."Organization"%ROWTYPE;
                BEGIN
                    -- Treat negative grant amounts as zero
                    grant_to_add := GREATEST(grant_to_add, 0);

                    -- Atomically update the organization's credits.
                    UPDATE {SCHEMA}."Organization"
                    SET
                        credit_grant = GREATEST(credit_grant + grant_to_add + LEAST(credit, 0), 0),
                        credit = CASE
                            -- Case 1: No debt. Credit is unchanged.
                            WHEN credit >= 0 THEN credit

                            -- Case 2: Debt exists
                            ELSE LEAST(credit + credit_grant + grant_to_add, 0)
                        END
                    WHERE id = organization_id
                    RETURNING * INTO updated_org;

                    RETURN updated_org;
                END;
                $$ LANGUAGE plpgsql;
            """)
        )
        await conn.commit()
    return False


async def _check_column_exists(
    conn: Connection,
    table_name: str,
    column_name: str,
) -> bool:
    sql = text(f"""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = '{SCHEMA}' AND table_name = '{table_name}' AND column_name = '{column_name}'
        LIMIT 1;
    """)
    exists = (await conn.execute(sql)).scalar()
    if exists:
        logger.info(f'Column "{column_name}" found in "{table_name}" table.')
        return True
    return False


async def _add_egress_updated_at_column(engine: AsyncEngine) -> bool:
    async with engine.connect() as conn:
        if await _check_column_exists(conn, "Organization", "egress_usage_updated_at"):
            return False
        await conn.execute(
            text(f"""
                ALTER TABLE {SCHEMA}."Organization"
                ADD COLUMN egress_usage_updated_at TIMESTAMPTZ DEFAULT NOW();
                """)
        )
        await conn.commit()
    return True


async def _add_project_description_column(engine: AsyncEngine) -> bool:
    """
    Add project description column.
    """
    table_name = "Project"
    column_name = "description"

    async with engine.connect() as conn:
        # Check if the column already exists
        if await _check_column_exists(conn, table_name, column_name):
            return False
        await conn.execute(
            text(
                f"""ALTER TABLE {SCHEMA}."{table_name}" ADD COLUMN {column_name} TEXT DEFAULT ''"""
            )
        )
        await conn.commit()
        logger.success(f'Successfully added column "{column_name}" to "{table_name}".')
        return True


async def _grant_auditor_privilege(engine: AsyncEngine) -> bool:
    """
    Apply the necessary grants to allow the auditor role to audit the database.
    """
    auditor_role = "jamaibase_auditor"
    audit_statement = "UPDATE, DELETE"
    async with engine.connect() as conn:
        role_exists = await conn.scalar(
            text(f"SELECT 1 FROM pg_roles WHERE rolname = '{auditor_role}'")
        )
        if role_exists is None:
            return False

        # alter default privileges for FUTURE tables
        await conn.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" '
                f"GRANT {audit_statement} ON TABLES TO {auditor_role};"
            )
        )

        # grant privileges for existing tables right now
        await conn.exec_driver_sql(
            f'GRANT {audit_statement} ON ALL TABLES IN SCHEMA "{SCHEMA}" TO {auditor_role};'
        )
        await conn.commit()
    return False


async def _migrate_verification_codes(engine: AsyncEngine) -> bool:
    """
    - Add columns:
        - `purpose`: str | None
        - `used_at`: DatetimeUTC | None
        - `revoked_at`: DatetimeUTC | None
    - If `meta` JSONB contains "purpose" key, update `purpose` column and delete "purpose" key
    """
    if ENV_CONFIG.is_oss:
        return False

    table_name = "VerificationCode"
    async with engine.connect() as conn:
        if (
            await _check_column_exists(conn, table_name, "purpose")
            and await _check_column_exists(conn, table_name, "revoked_at")
            and await _check_column_exists(conn, table_name, "used_at")
        ):
            return False
    async with engine.begin() as conn:
        await conn.execute(text(f'LOCK TABLE {SCHEMA}."{table_name}" IN SHARE MODE;'))
        # Add columns
        await conn.execute(
            text(
                f"""
                ALTER TABLE {SCHEMA}."{table_name}"
                ADD COLUMN IF NOT EXISTS purpose TEXT DEFAULT NULL,
                ADD COLUMN IF NOT EXISTS used_at TIMESTAMPTZ DEFAULT NULL,
                ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ DEFAULT NULL;
                """
            )
        )
        # If `meta` JSONB contains "purpose" key, update `purpose` column and delete "purpose" key
        await conn.execute(
            text(
                f"""
                UPDATE {SCHEMA}."{table_name}" SET purpose = meta ->> 'purpose' WHERE meta ->> 'purpose' IS NOT NULL;
                UPDATE {SCHEMA}."{table_name}" SET meta = meta - 'purpose' WHERE meta ->> 'purpose' IS NOT NULL;
                """
            )
        )
    logger.info(f'Successfully migrated "{table_name}".')
    return True


async def migrate_db():
    engine = create_db_engine_async()
    migrated = [
        await _create_schema(engine),
        await _grant_auditor_privilege(engine),
        await _create_tables(engine),
        await _create_pg_functions(engine),
        await _add_egress_updated_at_column(engine),
        await _add_project_description_column(engine),
        await _migrate_verification_codes(engine),
    ]
    if any(migrated):
        logger.success("DB migrations performed.")
    else:
        logger.success("No DB migrations performed.")
    # Clean up connection pool
    # https://docs.sqlalchemy.org/en/20/core/pooling.html#using-connection-pools-with-multiprocessing-or-os-fork
    await engine.dispose()
    # Always clear cache
    await CACHE.clear_all_async()
    await CACHE.aclose()


async def init_db(*, init_max_users: int = 3):
    from fastapi import Request
    from sqlmodel import func, select
    from starlette.datastructures import URL, Headers

    from owl.db.models import ModelConfig, Organization, User
    from owl.routers import models
    from owl.routers.organizations import oss as organizations_oss
    from owl.routers.projects import oss as projects_oss
    from owl.routers.users import oss as users_oss
    from owl.types import OrganizationRead, UserRead
    from owl.utils.exceptions import ResourceNotFoundError
    from owl.utils.test import (
        GPT_41_NANO_CONFIG,
        TEXT_EMBEDDING_3_SMALL_CONFIG,
        RERANK_ENGLISH_v3_SMALL_CONFIG,
    )

    async with async_session() as session:
        # As a safety measure, init DB only if it has less than `init_max_users` users
        # Just in case we accidentally tried to nuke a prod DB
        user_count = (await session.exec(select(func.count(User.id)))).one()
        if user_count >= init_max_users:
            logger.info(
                f"Found {user_count:,d} users, abort database initialisation (>= {init_max_users} users)."
            )
            return

        # Only enforce OSS check if db_init=False
        if ENV_CONFIG.is_oss and user_count != 0:
            logger.info("OSS mode: Skipping initialization (non-empty DB).")
            return

        logger.info("Initialising database...")

        # Create a mock Request object
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "headers": Headers({"content-type": "application/json"}).raw,
                "url": URL("/v2/users"),
                "state": {"id": uuid7_str()},
            }
        )

        # User
        try:
            user = await User.get(session, "0")
        except ResourceNotFoundError:
            await users_oss.create_user(
                request=request,
                token="",
                session=session,
                body=users_oss.UserCreate(
                    name="Admin user",
                    email="user@local.com",
                    password="jambubu",
                ),
            )
            user = await User.get(session, "0", populate_existing=True)

        # Manually verify email
        user.email_verified = True
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user = UserRead.model_validate(user)

        # Organization
        if await session.get(Organization, "0") is None:
            await organizations_oss.create_organization(
                request=request,
                user=user,
                body=organizations_oss.OrganizationCreate(
                    name="Admin org",
                    external_keys={
                        "anthropic": ENV_CONFIG.anthropic_api_key_plain,
                        "azure": ENV_CONFIG.azure_api_key_plain,
                        "azure_ai": ENV_CONFIG.azure_ai_api_key_plain,
                        "bedrock": ENV_CONFIG.bedrock_api_key_plain,
                        "cerebras": ENV_CONFIG.cerebras_api_key_plain,
                        "cohere": ENV_CONFIG.cohere_api_key_plain,
                        "deepseek": ENV_CONFIG.deepseek_api_key_plain,
                        "gemini": ENV_CONFIG.gemini_api_key_plain,
                        "groq": ENV_CONFIG.groq_api_key_plain,
                        "hyperbolic": ENV_CONFIG.hyperbolic_api_key_plain,
                        "jina_ai": ENV_CONFIG.jina_ai_api_key_plain,
                        "openai": ENV_CONFIG.openai_api_key_plain,
                        "openrouter": ENV_CONFIG.openrouter_api_key_plain,
                        "sagemaker": ENV_CONFIG.sagemaker_api_key_plain,
                        "sambanova": ENV_CONFIG.sambanova_api_key_plain,
                        "together_ai": ENV_CONFIG.together_ai_api_key_plain,
                        "vertex_ai": ENV_CONFIG.vertex_ai_api_key_plain,
                        "voyage": ENV_CONFIG.voyage_api_key_plain,
                    },
                ),
            )
        if ENV_CONFIG.is_oss:
            return
        # Continue creating sample data for Cloud mode
        user = UserRead.model_validate(await User.get(session, user.id, populate_existing=True))

        # Add credit grant
        org = await session.get(Organization, "0", populate_existing=True)
        org.credit_grant = 150.0
        session.add(org)
        await session.commit()
        await session.refresh(org)
        org = OrganizationRead.model_validate(org)

        # Project
        await projects_oss.create_project(
            request=request,
            user=user,
            session=session,
            body=projects_oss.ProjectCreate(
                organization_id=org.id,
                name="Admin project",
            ),
            project_id="proj_bee957b5881f35e120909510",
        )

        model_count = (await session.exec(select(func.count(ModelConfig.id)))).one()
        model_list: list[models.ModelConfig] = []
        if model_count == 0:
            # Chat models
            model_list.append(
                await models.create_model_config(
                    request=request,
                    user=user,
                    session=session,
                    body=GPT_41_NANO_CONFIG,
                )
            )
            # Embedding model
            model_list.append(
                await models.create_model_config(
                    request=request,
                    user=user,
                    session=session,
                    body=TEXT_EMBEDDING_3_SMALL_CONFIG,
                )
            )
            # Reranking model
            model_list.append(
                await models.create_model_config(
                    request=request,
                    user=user,
                    session=session,
                    body=RERANK_ENGLISH_v3_SMALL_CONFIG,
                )
            )

        # Model Deployments
        for model in model_list:
            provider = model.id.split("/")[0]
            # We need to deploy non-standard models manually
            if provider not in models.CloudProvider:
                continue
            await models.create_deployment(
                request=request,
                user=user,
                session=session,
                body=models.DeploymentCreate(
                    model_id=model.id,
                    name=f"{model.name} deployment 1",
                    provider=provider,
                    routing_id=model.id,
                    api_base="",
                ),
            )
