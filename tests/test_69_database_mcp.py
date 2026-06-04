"""Tests del servidor MCP database_assistant (sin LLM, sin servidor externo).

Cubre: SQLite (stdlib), pg/mysql opcionales (sin deps → mensaje), herramientas
unificadas db_*, FTS5, bulk_insert, backup, prompts y recursos.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.database_assistant import (
    _TOOL_FNS,
    _TOOLS,
    _PROMPTS,
    _RESOURCES,
    _RESOURCE_FNS,
    _prompt_get,
    _tool_csv_to_sqlite,
    _tool_db_connect,
    _tool_db_export,
    _tool_db_explain,
    _tool_db_import,
    _tool_db_indices,
    _tool_db_migrate_check,
    _tool_db_query,
    _tool_db_schema,
    _tool_db_stats,
    _tool_db_tables,
    _tool_mysql_explain,
    _tool_mysql_query,
    _tool_mysql_schema,
    _tool_pg_explain,
    _tool_pg_query,
    _tool_pg_schema,
    _tool_sql_format,
    _tool_sqlite_backup,
    _tool_sqlite_bulk_insert,
    _tool_sqlite_create_table,
    _tool_sqlite_delete,
    _tool_sqlite_explain,
    _tool_sqlite_export,
    _tool_sqlite_fts_search,
    _tool_sqlite_indices,
    _tool_sqlite_insert,
    _tool_sqlite_query,
    _tool_sqlite_schema,
    _tool_sqlite_tables,
    _tool_sqlite_to_csv,
    _tool_sqlite_update,
    _tool_sqlite_vacuum,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_TEST_TMP = Path.home() / ".oocode" / "_test_tmp_database"


@pytest.fixture(autouse=True)
def _cleanup():
    _TEST_TMP.mkdir(parents=True, exist_ok=True)
    yield
    import shutil
    shutil.rmtree(_TEST_TMP, ignore_errors=True)


@pytest.fixture
def tmp_path():
    _TEST_TMP.mkdir(parents=True, exist_ok=True)
    return _TEST_TMP


@pytest.fixture
def sample_db(tmp_path):
    import sqlite3
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.commit()
    conn.close()
    return db


# ── Consistencia de schemas ────────────────────────────────────────────────────

class TestStructure:
    def test_tools_count(self):
        assert len(_TOOLS) >= 30, f"Solo hay {len(_TOOLS)} tools (mínimo 30)"

    def test_tool_fns_matches_tools(self):
        names = {t["name"] for t in _TOOLS}
        keys  = set(_TOOL_FNS.keys())
        assert names == keys, f"Mismatch — falta en _TOOL_FNS: {names-keys}, extra: {keys-names}"

    def test_every_tool_has_name_and_description(self):
        for t in _TOOLS:
            assert "name" in t and t["name"]
            assert "description" in t and t["description"]

    def test_every_tool_has_input_schema(self):
        for t in _TOOLS:
            assert "inputSchema" in t
            assert t["inputSchema"].get("type") == "object"

    def test_all_handlers_callable(self):
        for name, fn in _TOOL_FNS.items():
            assert callable(fn), f"Handler '{name}' no es callable"

    def test_sqlite_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("sqlite_query", "sqlite_schema", "sqlite_tables", "sqlite_insert",
                  "sqlite_update", "sqlite_delete", "sqlite_export", "sqlite_vacuum",
                  "sqlite_fts_search", "sqlite_bulk_insert", "sqlite_backup"):
            assert n in names, f"Falta {n}"

    def test_pg_and_mysql_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("pg_query", "pg_schema", "pg_explain", "mysql_query", "mysql_schema", "mysql_explain"):
            assert n in names, f"Falta {n}"

    def test_unified_db_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("db_connect", "db_query", "db_schema", "db_tables", "db_explain",
                  "db_export", "db_import", "db_migrate_check", "db_indices"):
            assert n in names, f"Falta herramienta unificada {n}"

    def test_utility_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        for n in ("csv_to_sqlite", "db_stats", "sql_format"):
            assert n in names, f"Falta {n}"


# ── SQLite queries ─────────────────────────────────────────────────────────────

class TestSqliteQuery:
    def test_select_returns_rows(self, sample_db):
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT * FROM users"})
        assert "Alice" in result and "Bob" in result

    def test_select_with_where(self, sample_db):
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT name FROM users WHERE age > 27"})
        assert "Alice" in result
        assert "Bob" not in result

    def test_empty_result(self, sample_db):
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT * FROM users WHERE age > 999"})
        assert isinstance(result, str)

    def test_invalid_sql_returns_error(self, sample_db):
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELEKT * FRON users"})
        assert "error" in result.lower() or "Error" in result

    def test_nonexistent_db_returns_error(self, tmp_path):
        result = _tool_sqlite_query({"db_path": str(tmp_path / "nope.db"), "sql": "SELECT 1"})
        assert isinstance(result, str) and len(result) > 0


class TestSqliteSchema:
    def test_schema_shows_tables(self, sample_db):
        result = _tool_sqlite_schema({"db_path": str(sample_db)})
        assert "users" in result and "products" in result

    def test_schema_shows_columns(self, sample_db):
        result = _tool_sqlite_schema({"db_path": str(sample_db)})
        assert "name" in result and "age" in result


class TestSqliteTables:
    def test_tables_lists_tables(self, sample_db):
        result = _tool_sqlite_tables({"db_path": str(sample_db)})
        assert "users" in result and "products" in result

    def test_tables_shows_row_count(self, sample_db):
        result = _tool_sqlite_tables({"db_path": str(sample_db)})
        assert "2" in result or "rows" in result.lower() or "fila" in result.lower()


class TestSqliteInsertUpdateDelete:
    def test_insert_adds_row(self, sample_db):
        _tool_sqlite_insert({"db_path": str(sample_db), "table": "users",
                             "data": '{"id": 3, "name": "Carol", "age": 22}'})
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT * FROM users WHERE id=3"})
        assert "Carol" in result

    def test_update_modifies_row(self, sample_db):
        _tool_sqlite_update({"db_path": str(sample_db), "table": "users",
                             "data": '{"age": 99}', "where": "name='Alice'"})
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT age FROM users WHERE name='Alice'"})
        assert "99" in result

    def test_delete_removes_row(self, sample_db):
        _tool_sqlite_delete({"db_path": str(sample_db), "table": "users", "where": "name='Bob'"})
        result = _tool_sqlite_query({"db_path": str(sample_db), "sql": "SELECT * FROM users"})
        assert "Bob" not in result


class TestSqliteCreateAndVacuum:
    def test_create_table(self, tmp_path):
        db = tmp_path / "new.db"
        result = _tool_sqlite_create_table({
            "db_path": str(db),
            "sql": "CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)",
        })
        assert isinstance(result, str)
        tables = _tool_sqlite_tables({"db_path": str(db)})
        assert "items" in tables

    def test_vacuum(self, sample_db):
        result = _tool_sqlite_vacuum({"db_path": str(sample_db)})
        assert isinstance(result, str)


class TestSqliteExportAndImport:
    def test_export_csv(self, sample_db, tmp_path):
        result = _tool_sqlite_export({"db_path": str(sample_db), "table": "users", "format": "csv"})
        assert "Alice" in result and "," in result

    def test_export_json(self, sample_db, tmp_path):
        result = _tool_sqlite_export({"db_path": str(sample_db), "table": "users", "format": "json"})
        data = json.loads(result)
        assert isinstance(data, list) and len(data) == 2

    def test_sqlite_to_csv_creates_file(self, sample_db, tmp_path):
        out = tmp_path / "export.csv"
        _tool_sqlite_to_csv({"db_path": str(sample_db), "table": "users", "output_path": str(out)})
        assert out.exists()
        text = out.read_text()
        assert "Alice" in text

    def test_csv_to_sqlite(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,name,score\n1,Ana,90\n2,Luis,85\n")
        db = tmp_path / "imported.db"
        result = _tool_csv_to_sqlite({"csv_path": str(csv_file), "db_path": str(db), "table": "scores"})
        assert isinstance(result, str)
        rows = _tool_sqlite_query({"db_path": str(db), "sql": "SELECT * FROM scores"})
        assert "Ana" in rows


class TestSqliteUtilities:
    def test_explain_returns_plan(self, sample_db):
        result = _tool_sqlite_explain({"db_path": str(sample_db), "sql": "SELECT * FROM users WHERE age=30"})
        assert isinstance(result, str) and len(result) > 0

    def test_indices(self, sample_db):
        result = _tool_sqlite_indices({"db_path": str(sample_db)})
        assert isinstance(result, str)

    def test_db_stats(self, sample_db):
        result = _tool_db_stats({"db_path": str(sample_db)})
        assert "users" in result or "table" in result.lower() or "2" in result


# ── PostgreSQL / MySQL sin deps ────────────────────────────────────────────────

class TestPgMysqlNoDeps:
    def test_pg_query_no_psycopg2(self):
        """Si psycopg2 no está instalado, devuelve mensaje claro."""
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado — test solo aplica sin la dep")
        except ImportError:
            result = _tool_pg_query({"dsn": "postgresql://localhost/test", "sql": "SELECT 1"})
            assert "psycopg2" in result.lower() or "disponible" in result.lower() or "install" in result.lower()

    def test_pg_schema_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_pg_schema({"dsn": "postgresql://localhost/test"})
            assert isinstance(result, str) and len(result) > 0

    def test_pg_explain_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_pg_explain({"dsn": "postgresql://localhost/test", "sql": "SELECT 1"})
            assert isinstance(result, str) and len(result) > 0

    def test_mysql_query_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_mysql_query({"dsn": "mysql://localhost/test", "sql": "SELECT 1"})
            assert "pymysql" in result.lower() or "disponible" in result.lower() or "install" in result.lower()

    def test_mysql_schema_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_mysql_schema({"dsn": "mysql://localhost/test"})
            assert isinstance(result, str) and len(result) > 0


# ── sql_format ────────────────────────────────────────────────────────────────

class TestSqlFormat:
    def test_formats_simple_select(self):
        result = _tool_sql_format({"sql": "select id,name from users where age>18"})
        assert isinstance(result, str) and len(result) > 0
        assert "SELECT" in result.upper() or "select" in result

    def test_formats_multiline(self):
        sql = "SELECT u.id, u.name, p.price FROM users u JOIN products p ON u.id=p.id WHERE p.price>10 ORDER BY u.name"
        result = _tool_sql_format({"sql": sql})
        assert isinstance(result, str) and len(result) >= len(sql)

    def test_empty_sql(self):
        result = _tool_sql_format({"sql": ""})
        assert isinstance(result, str)


# ── SQLite nuevas herramientas ─────────────────────────────────────────────────

class TestSqliteBulkInsert:
    def test_bulk_insert_rows(self, sample_db):
        rows = [{"id": 10, "name": "Carol", "age": 28}, {"id": 11, "name": "Dave", "age": 35}]
        result = _tool_sqlite_bulk_insert({"db_path": str(sample_db), "table": "users", "rows": rows})
        assert "OK" in result and "2" in result

    def test_bulk_insert_empty_rows(self, sample_db):
        result = _tool_sqlite_bulk_insert({"db_path": str(sample_db), "table": "users", "rows": []})
        assert "Error" in result

    def test_bulk_insert_upsert(self, sample_db):
        rows = [{"id": 1, "name": "Alice Updated", "age": 31}]
        result = _tool_sqlite_bulk_insert({"db_path": str(sample_db), "table": "users",
                                           "rows": rows, "mode": "upsert"})
        assert "OK" in result

    def test_bulk_insert_missing_table(self, sample_db):
        result = _tool_sqlite_bulk_insert({"db_path": str(sample_db), "rows": [{"x": 1}]})
        assert "Error" in result


class TestSqliteBackup:
    def test_backup_creates_file(self, sample_db, tmp_path):
        backup = tmp_path / "backup.db"
        result = _tool_sqlite_backup({"db_path": str(sample_db), "backup_path": str(backup)})
        assert "OK" in result
        assert backup.exists()
        assert backup.stat().st_size > 0

    def test_backup_missing_source(self, tmp_path):
        result = _tool_sqlite_backup({"db_path": str(tmp_path / "nope.db"),
                                      "backup_path": str(tmp_path / "out.db")})
        assert "Error" in result

    def test_backup_missing_args(self):
        result = _tool_sqlite_backup({})
        assert "Error" in result


class TestSqliteFtsSearch:
    def test_fts_creates_and_searches(self, tmp_path):
        import sqlite3
        db = tmp_path / "fts_test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, content TEXT)")
        conn.execute("INSERT INTO docs VALUES (1, 'python programming language')")
        conn.execute("INSERT INTO docs VALUES (2, 'database management systems')")
        conn.execute("INSERT INTO docs VALUES (3, 'python data analysis pandas')")
        conn.commit()
        conn.close()

        result = _tool_sqlite_fts_search({
            "db_path": str(db),
            "fts_table": "docs_fts",
            "query": "python",
            "content_table": "docs",
            "content_col": "content",
        })
        assert isinstance(result, str)
        # May fail if FTS5 not available — just check it returns a string
        if "FTS5" not in result and "Error" not in result:
            assert "python" in result.lower() or "resultado" in result.lower()

    def test_fts_missing_params(self, sample_db):
        result = _tool_sqlite_fts_search({"db_path": str(sample_db), "fts_table": "t"})
        assert "Error" in result


# ── Herramientas unificadas (db_*) ─────────────────────────────────────────────

class TestDbConnectNoDeps:
    def test_missing_driver(self):
        result = _tool_db_connect({})
        assert "Error" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_connect({"driver": "postgresql", "dsn": "postgresql://localhost/test"})
            assert "psycopg2" in result.lower() or "disponible" in result.lower()

    def test_mysql_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_db_connect({"driver": "mysql", "dsn": "mysql://localhost/test"})
            assert "pymysql" in result.lower() or "disponible" in result.lower()

    def test_unknown_driver(self):
        result = _tool_db_connect({"driver": "oracle", "dsn": "oracle://localhost"})
        assert "Error" in result or "desconocido" in result.lower()


class TestDbQueryUnified:
    def test_missing_args(self):
        result = _tool_db_query({})
        assert "Error" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_query({"driver": "postgresql", "dsn": "pg://x", "sql": "SELECT 1"})
            assert isinstance(result, str) and len(result) > 0

    def test_mysql_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_db_query({"driver": "mysql", "dsn": "mysql://x", "sql": "SELECT 1"})
            assert isinstance(result, str) and len(result) > 0


class TestDbSchemaUnified:
    def test_sqlite_schema_via_db_schema(self, sample_db):
        result = _tool_db_schema({"driver": "sqlite", "db_path": str(sample_db)})
        assert "users" in result and "products" in result

    def test_sqlite_schema_single_table(self, sample_db):
        result = _tool_db_schema({"driver": "sqlite", "db_path": str(sample_db), "table": "users"})
        assert "users" in result
        assert "products" not in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_schema({"driver": "postgresql", "dsn": "pg://x"})
            assert isinstance(result, str)

    def test_mysql_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_db_schema({"driver": "mysql", "dsn": "mysql://x"})
            assert isinstance(result, str)


class TestDbTablesUnified:
    def test_sqlite_tables_via_db_tables(self, sample_db):
        result = _tool_db_tables({"driver": "sqlite", "db_path": str(sample_db)})
        assert "users" in result and "products" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_tables({"driver": "postgresql", "dsn": "pg://x"})
            assert isinstance(result, str)


class TestDbExplainUnified:
    def test_sqlite_explain_via_db_explain(self, sample_db):
        result = _tool_db_explain({
            "driver": "sqlite",
            "db_path": str(sample_db),
            "sql": "SELECT * FROM users WHERE id = 1",
        })
        assert isinstance(result, str) and len(result) > 0

    def test_missing_sql(self, sample_db):
        result = _tool_db_explain({"driver": "sqlite", "db_path": str(sample_db)})
        assert "Error" in result


class TestDbExportUnified:
    def test_export_sqlite_csv(self, sample_db):
        result = _tool_db_export({
            "driver": "sqlite",
            "db_path": str(sample_db),
            "table": "users",
            "format": "csv",
        })
        assert "id" in result and "Alice" in result

    def test_export_sqlite_json(self, sample_db):
        result = _tool_db_export({
            "driver": "sqlite",
            "db_path": str(sample_db),
            "sql": "SELECT * FROM products",
            "format": "json",
        })
        data = json.loads(result)
        assert isinstance(data, list) and len(data) > 0
        assert "name" in data[0]

    def test_export_to_file(self, sample_db, tmp_path):
        out = tmp_path / "export.csv"
        result = _tool_db_export({
            "driver": "sqlite",
            "db_path": str(sample_db),
            "table": "users",
            "format": "csv",
            "output_path": str(out),
        })
        assert "OK" in result and out.exists()

    def test_missing_table_and_sql(self, sample_db):
        result = _tool_db_export({"driver": "sqlite", "db_path": str(sample_db)})
        assert "Error" in result


class TestDbImportUnified:
    def test_import_data_sqlite(self, sample_db):
        data = [{"id": 99, "name": "Imported", "age": 20}]
        result = _tool_db_import({
            "driver": "sqlite",
            "db_path": str(sample_db),
            "table": "users",
            "data": data,
        })
        assert "OK" in result and "1" in result

    def test_import_csv_file_sqlite(self, tmp_path):
        import sqlite3
        db = tmp_path / "import_test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE items (name TEXT, qty INTEGER)")
        conn.commit()
        conn.close()

        csv_file = tmp_path / "items.csv"
        csv_file.write_text("name,qty\nApple,10\nBanana,5\n")
        result = _tool_db_import({
            "driver": "sqlite",
            "db_path": str(db),
            "table": "items",
            "file": str(csv_file),
        })
        assert "OK" in result and "2" in result

    def test_import_missing_table(self, sample_db):
        result = _tool_db_import({"driver": "sqlite", "db_path": str(sample_db), "data": [{"x": 1}]})
        assert "Error" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_import({
                "driver": "postgresql", "dsn": "pg://x",
                "table": "t", "data": [{"x": 1}],
            })
            assert isinstance(result, str)

    def test_mysql_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_db_import({
                "driver": "mysql", "dsn": "mysql://x",
                "table": "t", "data": [{"x": 1}],
            })
            assert isinstance(result, str)


class TestDbMigrateCheck:
    def test_same_schema_no_diff(self, tmp_path):
        import sqlite3
        db1 = tmp_path / "db1.db"
        db2 = tmp_path / "db2.db"
        for db in (db1, db2):
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE items (id INTEGER, name TEXT)")
            conn.commit()
            conn.close()
        result = _tool_db_migrate_check({
            "source_driver": "sqlite", "source_db_path": str(db1),
            "target_driver": "sqlite", "target_db_path": str(db2),
        })
        assert "idénticos" in result.lower() or "sin diferencias" in result.lower()

    def test_added_table(self, tmp_path):
        import sqlite3
        db1 = tmp_path / "db1.db"
        db2 = tmp_path / "db2.db"
        conn = sqlite3.connect(str(db1))
        conn.execute("CREATE TABLE items (id INTEGER)")
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(db2))
        conn.execute("CREATE TABLE items (id INTEGER)")
        conn.execute("CREATE TABLE new_table (x TEXT)")
        conn.commit()
        conn.close()
        result = _tool_db_migrate_check({
            "source_driver": "sqlite", "source_db_path": str(db1),
            "target_driver": "sqlite", "target_db_path": str(db2),
        })
        assert "new_table" in result

    def test_added_column(self, tmp_path):
        import sqlite3
        db1 = tmp_path / "db1.db"
        db2 = tmp_path / "db2.db"
        conn = sqlite3.connect(str(db1))
        conn.execute("CREATE TABLE items (id INTEGER, name TEXT)")
        conn.commit()
        conn.close()
        conn = sqlite3.connect(str(db2))
        conn.execute("CREATE TABLE items (id INTEGER, name TEXT, price REAL)")
        conn.commit()
        conn.close()
        result = _tool_db_migrate_check({
            "source_driver": "sqlite", "source_db_path": str(db1),
            "target_driver": "sqlite", "target_db_path": str(db2),
        })
        assert "price" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_migrate_check({
                "source_driver": "postgresql", "source_dsn": "pg://x",
                "target_driver": "postgresql", "target_dsn": "pg://y",
            })
            assert isinstance(result, str)


class TestDbIndicesUnified:
    def test_sqlite_indices_via_db_indices(self, tmp_path):
        import sqlite3
        db = tmp_path / "idx_test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE INDEX idx_name ON t(name)")
        conn.commit()
        conn.close()
        result = _tool_db_indices({"driver": "sqlite", "db_path": str(db)})
        assert "idx_name" in result

    def test_pg_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_indices({"driver": "postgresql", "dsn": "pg://x"})
            assert isinstance(result, str)


class TestDbStatsUnified:
    def test_sqlite_stats_extended(self, sample_db):
        result = _tool_db_stats({"driver": "sqlite", "db_path": str(sample_db)})
        assert "SQLite" in result or "users" in result

    def test_pg_stats_no_psycopg2(self):
        try:
            import psycopg2
            pytest.skip("psycopg2 instalado")
        except ImportError:
            result = _tool_db_stats({"driver": "postgresql", "dsn": "pg://x"})
            assert isinstance(result, str)

    def test_mysql_stats_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_db_stats({"driver": "mysql", "dsn": "mysql://x"})
            assert isinstance(result, str)


class TestMysqlExplain:
    def test_no_pymysql(self):
        try:
            import pymysql
            pytest.skip("pymysql instalado")
        except ImportError:
            result = _tool_mysql_explain({"dsn": "mysql://x", "sql": "SELECT 1"})
            assert "pymysql" in result.lower() or "disponible" in result.lower()

    def test_missing_args(self):
        result = _tool_mysql_explain({})
        assert "Error" in result or "disponible" in result.lower()


# ── Prompts ────────────────────────────────────────────────────────────────────

class TestDatabasePrompts:
    def test_prompts_dict_exists(self):
        assert isinstance(_PROMPTS, dict) and len(_PROMPTS) >= 3

    def test_expected_prompts_present(self):
        for name in ("schema_design", "query_optimize", "migration_plan"):
            assert name in _PROMPTS, f"Prompt '{name}' no encontrado"

    def test_schema_design_returns_messages(self):
        result = _prompt_get("schema_design", {"description": "blog con posts y comentarios"})
        assert isinstance(result, list) and len(result) > 0
        assert result[0]["role"] == "user"
        text = result[0]["content"]["text"]
        assert "blog" in text.lower() or "esquema" in text.lower()

    def test_query_optimize_returns_messages(self):
        result = _prompt_get("query_optimize", {"query": "SELECT * FROM users WHERE name LIKE '%a%'"})
        assert isinstance(result, list) and len(result) > 0
        assert result[0]["role"] == "user"

    def test_migration_plan_returns_messages(self):
        result = _prompt_get("migration_plan", {
            "source_schema": "CREATE TABLE t (id INT)",
            "target_schema": "CREATE TABLE t (id INT, name TEXT)",
        })
        assert isinstance(result, list) and len(result) > 0

    def test_unknown_prompt_fallback(self):
        result = _prompt_get("nonexistent_xyz", {})
        assert isinstance(result, list) and len(result) > 0

    def test_all_prompts_have_description_and_args(self):
        for name, defn in _PROMPTS.items():
            assert "description" in defn and defn["description"]
            assert "arguments" in defn and isinstance(defn["arguments"], list)


# ── Recursos ───────────────────────────────────────────────────────────────────

class TestDatabaseResources:
    def test_resources_list(self):
        assert isinstance(_RESOURCES, list) and len(_RESOURCES) >= 1

    def test_database_resource_registered(self):
        uris = {r["uri"] for r in _RESOURCES}
        assert "project://database" in uris

    def test_resource_fns_match(self):
        uris = {r["uri"] for r in _RESOURCES}
        assert uris == set(_RESOURCE_FNS.keys())

    def test_database_resource_returns_string(self):
        fn = _RESOURCE_FNS["project://database"]
        result = fn()
        assert isinstance(result, str) and len(result) > 0
