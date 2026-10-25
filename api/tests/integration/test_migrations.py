import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.models import Base
from tests.integration.conftest import alembic_config


def test_migrations_create_the_expected_tables(postgres_url):
    engine = create_engine(postgres_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert {"projects", "volumes", "llm_calls", "alembic_version"} <= tables


def test_migrations_match_the_models(postgres_url):
    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()

    assert diff == []


def test_downgrade_and_upgrade_round_trip(postgres_url):
    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(postgres_url)
    assert {"projects", "volumes", "llm_calls"} <= set(inspect(engine).get_table_names())
    engine.dispose()


BEFORE_PROJECTS = "7c3e91a5d2b4"  # the revision just before projects existed
BEFORE_SLUGS = "b5d8a3c1e7f2"  # projects exist, without a slug


def empty_tables(url):
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE llm_calls, volumes, projects RESTART IDENTITY CASCADE"))
    engine.dispose()


def test_existing_volumes_move_into_the_default_project(postgres_url):
    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)
    command.downgrade(cfg, BEFORE_PROJECTS)
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO volumes (name) VALUES ('alice-chat-42'), ('team/support')")
            )
            conn.execute(
                text(
                    "INSERT INTO llm_calls (volume_id, trace_id, span_id, app_name, started_at,"
                    " status, trace_key) SELECT id, repeat('a', 32), repeat('b', 16), 'my-bot',"
                    " now(), 'ok', 'volumes/alice-chat-42/x.json' FROM volumes"
                    " WHERE name = 'alice-chat-42'"
                )
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            projects = conn.execute(text("SELECT id, name FROM projects")).all()
            volumes = conn.execute(
                text(
                    "SELECT v.name, p.name FROM volumes v JOIN projects p ON p.id = v.project_id"
                    " ORDER BY v.name"
                )
            ).all()
            calls = conn.execute(text("SELECT count(*) FROM llm_calls")).scalar_one()
        assert [name for _, name in projects] == ["default"]
        assert volumes == [("alice-chat-42", "default"), ("team/support", "default")]
        assert calls == 1
        assert "app_name" not in {c["name"] for c in inspect(engine).get_columns("llm_calls")}
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        empty_tables(postgres_url)


def test_a_fresh_database_has_the_default_project(postgres_url):
    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(postgres_url)
    with engine.connect() as conn:
        names = conn.execute(text("SELECT name FROM projects")).scalars().all()
    engine.dispose()

    assert names == ["default"]


def test_the_same_volume_name_can_exist_in_two_projects_but_not_twice_in_one(postgres_url):
    from sqlalchemy.exc import IntegrityError

    empty_tables(postgres_url)
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO projects (name, slug) VALUES ('a', 'a'), ('b', 'b')"))
            conn.execute(
                text("INSERT INTO volumes (project_id, name) SELECT id, 'chat' FROM projects")
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO volumes (project_id, name) SELECT id, 'chat' FROM projects"
                        " WHERE name = 'a'"
                    )
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO projects (name, slug) VALUES ('a', 'other')"))
    finally:
        engine.dispose()
        empty_tables(postgres_url)


def test_downgrade_refuses_when_a_volume_name_is_in_several_projects(postgres_url):
    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO projects (name, slug) VALUES ('a', 'a'), ('b', 'b')"))
            conn.execute(
                text("INSERT INTO volumes (project_id, name) SELECT id, 'chat' FROM projects")
            )

        with pytest.raises(Exception, match="several projects"):
            command.downgrade(cfg, BEFORE_PROJECTS)

        # nothing was changed: the database is still at the head revision
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM projects")).scalar_one() == 2
    finally:
        engine.dispose()
        empty_tables(postgres_url)


def test_existing_projects_get_a_slug_made_from_their_name(postgres_url):
    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)
    command.downgrade(cfg, BEFORE_SLUGS)
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO projects (name) VALUES ('default'), ('Support Desk'), "
                    "('support desk'), ('Café Bot'), ('日本語'), ('!!!')"
                )
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT name, slug FROM projects")).all())
        assert rows == {
            "default": "default",
            "Support Desk": "support-desk",
            "support desk": "support-desk-2",  # the same slug as "Support Desk": numbered
            "Café Bot": "cafe-bot",
            "日本語": "project",
            "!!!": "project-2",
        }
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        empty_tables(postgres_url)


def test_the_slug_is_required_and_unique(postgres_url):
    from sqlalchemy.exc import IntegrityError

    empty_tables(postgres_url)
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO projects (name, slug) VALUES ('A', 'a')"))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO projects (name, slug) VALUES ('B', 'a')"))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO projects (name) VALUES ('C')"))
    finally:
        engine.dispose()
        empty_tables(postgres_url)


def test_downgrading_drops_the_slug(postgres_url):
    from sqlalchemy import inspect

    cfg = alembic_config(postgres_url)
    empty_tables(postgres_url)
    command.downgrade(cfg, BEFORE_SLUGS)
    engine = create_engine(postgres_url)
    try:
        assert "slug" not in {c["name"] for c in inspect(engine).get_columns("projects")}
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
        empty_tables(postgres_url)
