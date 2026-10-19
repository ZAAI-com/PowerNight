"""
Regression tests for database migration.

Covers:
- Migrations are idempotent (running twice must not fail or duplicate data)
- Built-in preset seeding never creates duplicates
- The legacy schedule_entries table is removed
"""

import pytest
from sqlalchemy import text


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Point the database layer at a fresh temp directory."""
    import powernight.core.database.connection as connection

    monkeypatch.setenv('POWERNIGHT_DATA_PATH', str(tmp_path))
    connection.close_database()
    yield connection
    connection.close_database()


@pytest.mark.unit
class TestMigrationIdempotency:

    def test_run_migration_twice_succeeds(self, fresh_db):
        from powernight.core.database.migration import run_migration

        assert run_migration() is True
        assert run_migration() is True

    def test_preset_seeding_never_duplicates(self, fresh_db):
        from powernight.core.database.migration import run_migration, BUILTIN_PRESETS

        run_migration()
        run_migration()
        run_migration()

        manager = fresh_db.get_database_manager()
        with manager.get_session_context() as session:
            rows = session.execute(text(
                "SELECT name, COUNT(*) FROM task_presets GROUP BY name HAVING COUNT(*) > 1"
            )).fetchall()
            assert rows == [], f"duplicate presets found: {rows}"

            total = session.execute(text("SELECT COUNT(*) FROM task_presets")).scalar()
            assert total == len(BUILTIN_PRESETS)

    def test_unique_index_blocks_concurrent_duplicates(self, fresh_db):
        from powernight.core.database.migration import run_migration
        from sqlalchemy.exc import IntegrityError

        run_migration()

        manager = fresh_db.get_database_manager()
        with pytest.raises(IntegrityError):
            with manager.get_session_context() as session:
                session.execute(text(
                    "INSERT INTO task_presets (id, name, command) "
                    "VALUES ('dup-test', 'Night Charge to 100%', 'reserve')"
                ))

    def test_legacy_schedule_entries_table_removed(self, fresh_db):
        from powernight.core.database.migration import run_migration

        manager = fresh_db.get_database_manager()
        # Simulate an old installation that still has the legacy table
        with manager.get_session_context() as session:
            session.execute(text(
                "CREATE TABLE IF NOT EXISTS schedule_entries (id TEXT PRIMARY KEY)"
            ))

        run_migration()

        with manager.get_session_context() as session:
            row = session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_entries'"
            )).fetchone()
            assert row is None, "legacy schedule_entries table should be dropped"
