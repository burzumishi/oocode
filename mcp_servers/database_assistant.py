#!/usr/bin/env python3
"""Database assistant MCP server — SQLite, PostgreSQL (optional), MySQL (optional).

Protocolo: MCP 2024-11-05 sobre stdio (JSON-RPC 2.0 newline-delimited JSON).

Tools:
  sqlite_query, sqlite_schema, sqlite_tables, sqlite_export, sqlite_insert,
  sqlite_update, sqlite_delete, sqlite_vacuum, sqlite_create_table,
  sqlite_indices, sqlite_explain,
  pg_query, pg_schema, pg_explain,
  mysql_query, mysql_schema,
  csv_to_sqlite, sqlite_to_csv, db_stats, sql_format
"""
import csv
import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional


# ── Helpers de protocolo MCP ──────────────────────────────────────────────────

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _recv() -> Optional[dict]:
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue


def _ok(req_id: Any, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id,
           "error": {"code": code, "message": message}})


# ── Helpers internos ──────────────────────────────────────────────────────────

def _ascii_table(headers: list[str], rows: list[tuple]) -> str:
    """Formatea filas como tabla ASCII con columnas alineadas."""
    if not rows and not headers:
        return "(sin resultados)"
    col_widths = [len(str(h)) for h in headers]
    str_rows = [[str(v) if v is not None else "NULL" for v in row] for row in rows]
    for row in str_rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    def fmt_row(cells: list[str]) -> str:
        return "|" + "|".join(f" {c:<{col_widths[i]}} " for i, c in enumerate(cells)) + "|"
    lines = [sep, fmt_row([str(h) for h in headers]), sep]
    for row in str_rows:
        lines.append(fmt_row(row))
    lines.append(sep)
    lines.append(f"({len(rows)} fila(s))")
    return "\n".join(lines)


def _sqlite_connect(db_path: str) -> tuple:
    """Abre conexión SQLite. Devuelve (conn, err_str)."""
    if not db_path:
        return None, "Error: 'db_path' requerido."
    p = Path(db_path).expanduser()
    try:
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        return conn, ""
    except Exception as exc:
        return None, f"Error abriendo '{db_path}': {exc}"


# ── SQLite tools ──────────────────────────────────────────────────────────────

def _tool_sqlite_query(args: dict) -> str:
    """Ejecuta una query SELECT en una base de datos SQLite y devuelve tabla ASCII.

    Args:
        db_path (str): Ruta al fichero .db de SQLite.
        sql     (str): Sentencia SQL a ejecutar (normalmente SELECT).
        params  (list): Parámetros posicionales opcionales para la query.
    """
    db_path = args.get("db_path", "")
    sql     = args.get("sql", "").strip()
    params  = args.get("params", []) or []

    if not sql:
        return "Error: 'sql' requerido."
    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchmany(1000)
        if cur.description is None:
            conn.commit()
            return f"OK: {conn.total_changes} fila(s) afectada(s)."
        headers = [d[0] for d in cur.description]
        result = _ascii_table(headers, [tuple(r) for r in rows])
        if len(rows) == 1000:
            result += "\n[limitado a 1000 filas]"
        return result
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_schema(args: dict) -> str:
    """Muestra el CREATE TABLE de todas las tablas de una base de datos SQLite.

    Args:
        db_path (str): Ruta al fichero .db de SQLite.
    """
    conn, err = _sqlite_connect(args.get("db_path", ""))
    if err:
        return err
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        if not rows:
            return "(sin tablas)"
        parts = []
        for name, sql in rows:
            parts.append(f"-- Tabla: {name}\n{sql or '(sin DDL)'};")
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


def _tool_sqlite_tables(args: dict) -> str:
    """Lista las tablas de una base de datos SQLite con conteo de filas.

    Args:
        db_path (str): Ruta al fichero .db de SQLite.
    """
    conn, err = _sqlite_connect(args.get("db_path", ""))
    if err:
        return err
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        if not tables:
            return "(sin tablas)"
        lines = [f"{'Tabla':<40} {'Filas':>8}"]
        lines.append("-" * 50)
        for (tname,) in tables:
            try:
                cnt = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
            except Exception:
                cnt = "?"
            lines.append(f"{tname:<40} {str(cnt):>8}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


def _tool_sqlite_export(args: dict) -> str:
    """Exporta una tabla de SQLite a CSV o JSON (devuelve el contenido como texto).

    Args:
        db_path (str): Ruta al fichero .db.
        table   (str): Nombre de la tabla a exportar.
        format  (str): 'csv' (default) o 'json'.
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    fmt     = args.get("format", "csv").lower()

    if not table:
        return "Error: 'table' requerido."
    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        cur = conn.execute(f'SELECT * FROM "{table}"')
        headers = [d[0] for d in cur.description]
        rows = [tuple(r) for r in cur.fetchall()]
        if fmt == "json":
            data = [dict(zip(headers, r)) for r in rows]
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        else:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows(rows)
            return buf.getvalue()
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_insert(args: dict) -> str:
    """Inserta una fila en una tabla SQLite.

    Args:
        db_path (str):  Ruta al fichero .db.
        table   (str):  Nombre de la tabla.
        data    (dict|str): Objeto JSON con columna→valor.
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    data    = args.get("data", {})

    if not table:
        return "Error: 'table' requerido."
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return "Error: 'data' debe ser un objeto JSON."
    if not isinstance(data, dict) or not data:
        return "Error: 'data' debe ser un objeto JSON no vacío."

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        cols = ", ".join(f'"{k}"' for k in data.keys())
        placeholders = ", ".join("?" for _ in data)
        sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
        conn.execute(sql, list(data.values()))
        conn.commit()
        return f"OK: fila insertada en '{table}'. rowid={conn.execute('SELECT last_insert_rowid()').fetchone()[0]}"
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_update(args: dict) -> str:
    """Actualiza filas en una tabla SQLite con un WHERE.

    Args:
        db_path (str):  Ruta al fichero .db.
        table   (str):  Nombre de la tabla.
        data    (dict): Columnas y valores a actualizar.
        where   (str):  Cláusula WHERE (sin la palabra WHERE), ej. "id = 5".
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    data    = args.get("data", {})
    where   = args.get("where", "")

    if not table:
        return "Error: 'table' requerido."
    if not where:
        return "Error: 'where' requerido (para seguridad, no se permite UPDATE sin WHERE)."
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return "Error: 'data' debe ser un objeto JSON."
    if not isinstance(data, dict) or not data:
        return "Error: 'data' debe ser un objeto JSON no vacío."

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        set_clause = ", ".join(f'"{k}" = ?' for k in data.keys())
        sql = f'UPDATE "{table}" SET {set_clause} WHERE {where}'
        cur = conn.execute(sql, list(data.values()))
        conn.commit()
        return f"OK: {cur.rowcount} fila(s) actualizada(s) en '{table}'."
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_delete(args: dict) -> str:
    """Elimina filas de una tabla SQLite que cumplan el WHERE.

    Args:
        db_path (str): Ruta al fichero .db.
        table   (str): Nombre de la tabla.
        where   (str): Cláusula WHERE (sin WHERE), ej. "id = 5".
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    where   = args.get("where", "")

    if not table:
        return "Error: 'table' requerido."
    if not where:
        return "Error: 'where' requerido (para seguridad, no se permite DELETE sin WHERE)."

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        cur = conn.execute(f'DELETE FROM "{table}" WHERE {where}')
        conn.commit()
        return f"OK: {cur.rowcount} fila(s) eliminada(s) de '{table}'."
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_vacuum(args: dict) -> str:
    """Ejecuta VACUUM + ANALYZE en una base de datos SQLite para optimizarla.

    Args:
        db_path (str): Ruta al fichero .db.
    """
    conn, err = _sqlite_connect(args.get("db_path", ""))
    if err:
        return err
    try:
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        conn.commit()
        return "OK: VACUUM y ANALYZE completados."
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


def _tool_sqlite_create_table(args: dict) -> str:
    """Ejecuta una sentencia CREATE TABLE en una base de datos SQLite.

    Args:
        db_path (str): Ruta al fichero .db (se crea si no existe).
        sql     (str): Sentencia CREATE TABLE completa.
    """
    db_path = args.get("db_path", "")
    sql     = args.get("sql", "").strip()

    if not sql:
        return "Error: 'sql' requerido."
    if not sql.upper().startswith("CREATE"):
        return "Error: la sentencia debe empezar con CREATE."

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        conn.execute(sql)
        conn.commit()
        return "OK: tabla creada."
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_indices(args: dict) -> str:
    """Lista los índices de una base de datos SQLite, opcionalmente filtrados por tabla.

    Args:
        db_path (str): Ruta al fichero .db.
        table   (str): Tabla específica (vacío = todos los índices).
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        if table:
            rows = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? ORDER BY name",
                (table,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name"
            ).fetchall()
        if not rows:
            return "(sin índices)"
        lines = []
        for row in rows:
            if table:
                lines.append(f"{row[0]}: {row[1] or '(índice automático)'}")
            else:
                lines.append(f"{row[0]}  [tabla: {row[1]}]  {row[2] or '(automático)'}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


def _tool_sqlite_explain(args: dict) -> str:
    """Muestra el plan de ejecución de una query SQLite (EXPLAIN QUERY PLAN).

    Args:
        db_path (str): Ruta al fichero .db.
        sql     (str): Sentencia SQL a analizar.
    """
    db_path = args.get("db_path", "")
    sql     = args.get("sql", "").strip()

    if not sql:
        return "Error: 'sql' requerido."
    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        if not rows:
            return "(sin plan)"
        lines = [f"{'id':>4}  {'parent':>6}  {'notused':>7}  detalle"]
        lines.append("-" * 70)
        for row in rows:
            lines.append(f"{row[0]:>4}  {row[1]:>6}  {row[2]:>7}  {row[3]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


# ── PostgreSQL tools (opcional) ───────────────────────────────────────────────

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False

_PG_NOT_AVAILABLE = "PostgreSQL no disponible — instala psycopg2: pip install psycopg2-binary"


def _tool_pg_query(args: dict) -> str:
    """Ejecuta una query SELECT en PostgreSQL y devuelve tabla ASCII.

    Args:
        dsn (str): DSN de conexión, ej. 'postgresql://user:pass@host/db' o
                   'host=localhost dbname=mydb user=postgres'.
        sql (str): Sentencia SQL a ejecutar.
    """
    if not _PSYCOPG2_OK:
        return _PG_NOT_AVAILABLE
    dsn = args.get("dsn", "")
    sql = args.get("sql", "").strip()
    if not dsn or not sql:
        return "Error: 'dsn' y 'sql' requeridos."
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description is None:
            conn.commit()
            return f"OK: {cur.rowcount} fila(s) afectada(s)."
        headers = [d[0] for d in cur.description]
        rows = cur.fetchmany(1000)
        result = _ascii_table(headers, rows)
        if len(rows) == 1000:
            result += "\n[limitado a 1000 filas]"
        conn.close()
        return result
    except Exception as exc:
        return f"Error PostgreSQL: {exc}"


def _tool_pg_schema(args: dict) -> str:
    """Lista tablas y columnas de una base de datos PostgreSQL.

    Args:
        dsn (str): DSN de conexión PostgreSQL.
    """
    if not _PSYCOPG2_OK:
        return _PG_NOT_AVAILABLE
    dsn = args.get("dsn", "")
    if not dsn:
        return "Error: 'dsn' requerido."
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return "(sin tablas en schema 'public')"
        current_table = None
        lines = []
        for tname, cname, dtype, nullable in rows:
            if tname != current_table:
                if current_table is not None:
                    lines.append("")
                lines.append(f"## {tname}")
                current_table = tname
            null_str = "NULL" if nullable == "YES" else "NOT NULL"
            lines.append(f"  {cname:<30} {dtype:<20} {null_str}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error PostgreSQL: {exc}"


def _tool_pg_explain(args: dict) -> str:
    """Muestra EXPLAIN ANALYZE de una query PostgreSQL.

    Args:
        dsn (str): DSN de conexión PostgreSQL.
        sql (str): Sentencia SQL a analizar.
    """
    if not _PSYCOPG2_OK:
        return _PG_NOT_AVAILABLE
    dsn = args.get("dsn", "")
    sql = args.get("sql", "").strip()
    if not dsn or not sql:
        return "Error: 'dsn' y 'sql' requeridos."
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(f"EXPLAIN ANALYZE {sql}")
        rows = cur.fetchall()
        conn.close()
        return "\n".join(r[0] for r in rows)
    except Exception as exc:
        return f"Error PostgreSQL: {exc}"


# ── MySQL tools (opcional) ────────────────────────────────────────────────────

try:
    import pymysql
    _PYMYSQL_OK = True
except ImportError:
    _PYMYSQL_OK = False

_MYSQL_NOT_AVAILABLE = "MySQL no disponible — instala pymysql: pip install pymysql"


def _parse_mysql_dsn(dsn: str) -> dict:
    """Parsea DSN tipo 'mysql://user:pass@host:3306/db' o 'host=... user=...'."""
    if dsn.startswith("mysql://") or dsn.startswith("mysql+pymysql://"):
        from urllib.parse import urlparse
        u = urlparse(dsn.replace("mysql+pymysql://", "mysql://"))
        return {
            "host":   u.hostname or "localhost",
            "port":   u.port or 3306,
            "user":   u.username or "",
            "password": u.password or "",
            "database": u.path.lstrip("/") if u.path else "",
        }
    # key=value format
    result: dict = {"host": "localhost", "port": 3306}
    for part in dsn.split():
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    if "dbname" in result:
        result["database"] = result.pop("dbname")
    return result


def _tool_mysql_query(args: dict) -> str:
    """Ejecuta una query SELECT en MySQL y devuelve tabla ASCII.

    Args:
        dsn (str): DSN de conexión, ej. 'mysql://user:pass@host/db'.
        sql (str): Sentencia SQL a ejecutar.
    """
    if not _PYMYSQL_OK:
        return _MYSQL_NOT_AVAILABLE
    dsn = args.get("dsn", "")
    sql = args.get("sql", "").strip()
    if not dsn or not sql:
        return "Error: 'dsn' y 'sql' requeridos."
    try:
        params = _parse_mysql_dsn(dsn)
        conn = pymysql.connect(**params, cursorclass=pymysql.cursors.Cursor)
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description is None:
            conn.commit()
            conn.close()
            return f"OK: {cur.rowcount} fila(s) afectada(s)."
        headers = [d[0] for d in cur.description]
        rows = cur.fetchmany(1000)
        conn.close()
        result = _ascii_table(headers, rows)
        if len(rows) == 1000:
            result += "\n[limitado a 1000 filas]"
        return result
    except Exception as exc:
        return f"Error MySQL: {exc}"


def _tool_mysql_schema(args: dict) -> str:
    """Lista tablas y columnas de una base de datos MySQL.

    Args:
        dsn (str): DSN de conexión MySQL.
    """
    if not _PYMYSQL_OK:
        return _MYSQL_NOT_AVAILABLE
    dsn = args.get("dsn", "")
    if not dsn:
        return "Error: 'dsn' requerido."
    try:
        params = _parse_mysql_dsn(dsn)
        db = params.get("database", "")
        conn = pymysql.connect(**params, cursorclass=pymysql.cursors.Cursor)
        cur = conn.cursor()
        cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """, (db,))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return f"(sin tablas en '{db}')"
        current_table = None
        lines = []
        for tname, cname, dtype, nullable in rows:
            if tname != current_table:
                if current_table is not None:
                    lines.append("")
                lines.append(f"## {tname}")
                current_table = tname
            null_str = "NULL" if nullable == "YES" else "NOT NULL"
            lines.append(f"  {cname:<30} {dtype:<20} {null_str}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error MySQL: {exc}"


# ── Utilidades cross-DB ───────────────────────────────────────────────────────

def _tool_csv_to_sqlite(args: dict) -> str:
    """Importa un fichero CSV a una tabla de SQLite (crea la tabla automáticamente).

    Args:
        csv_path (str):  Ruta al fichero CSV.
        db_path  (str):  Ruta al fichero .db de SQLite (se crea si no existe).
        table    (str):  Nombre de la tabla de destino.
    """
    csv_path = args.get("csv_path", "")
    db_path  = args.get("db_path", "")
    table    = args.get("table", "")

    if not csv_path or not db_path or not table:
        return "Error: 'csv_path', 'db_path' y 'table' requeridos."

    p = Path(csv_path).expanduser()
    if not p.exists():
        return f"Error: '{csv_path}' no existe."

    try:
        with open(p, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return "Error: el CSV está vacío."
            headers = list(rows[0].keys())

        conn, err = _sqlite_connect(db_path)
        if err:
            return err

        cols_ddl = ", ".join(f'"{h}" TEXT' for h in headers)
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols_ddl})')
        conn.commit()

        placeholders = ", ".join("?" for _ in headers)
        sql = f'INSERT INTO "{table}" VALUES ({placeholders})'
        conn.executemany(sql, [[r.get(h, "") for h in headers] for r in rows])
        conn.commit()
        conn.close()
        return f"OK: {len(rows)} filas importadas a '{table}' en '{db_path}'."
    except Exception as exc:
        return f"Error importando CSV: {exc}"


def _tool_sqlite_to_csv(args: dict) -> str:
    """Exporta una tabla SQLite a un fichero CSV.

    Args:
        db_path     (str): Ruta al fichero .db.
        table       (str): Nombre de la tabla.
        output_path (str): Ruta del fichero CSV de salida.
    """
    db_path     = args.get("db_path", "")
    table       = args.get("table", "")
    output_path = args.get("output_path", "")

    if not table or not output_path:
        return "Error: 'table' y 'output_path' requeridos."

    content = _tool_sqlite_export({"db_path": db_path, "table": table, "format": "csv"})
    if content.startswith("Error"):
        return content

    out = Path(output_path).expanduser()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        row_count = content.count("\n") - 1
        return f"OK: {row_count} filas exportadas a '{output_path}'."
    except Exception as exc:
        return f"Error escribiendo CSV: {exc}"


def _tool_db_stats(args: dict) -> str:
    """Muestra estadísticas de una base de datos: tamaño, tablas, filas, versión.

    SQLite: usa db_path. PostgreSQL/MySQL: usa driver + dsn.

    Args:
        db_path (str): Ruta al fichero .db de SQLite (si driver='sqlite').
        driver  (str): 'sqlite' (default), 'postgresql' o 'mysql'.
        dsn     (str): DSN de conexión para PostgreSQL o MySQL.
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    db_path = args.get("db_path", "")
    dsn     = args.get("dsn", "")

    # ── PostgreSQL ──────────────────────────────────────────────────────────────
    if driver in ("postgresql", "postgres", "pg"):
        if not _PSYCOPG2_OK:
            return _PG_NOT_AVAILABLE
        if not dsn:
            return "Error: 'dsn' requerido para PostgreSQL."
        try:
            conn = psycopg2.connect(dsn)
            cur = conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.execute("""
                SELECT table_name,
                       pg_size_pretty(pg_total_relation_size(quote_ident(table_name))),
                       pg_total_relation_size(quote_ident(table_name))
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY 3 DESC
            """)
            tables = cur.fetchall()
            cur.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database())),
                       pg_database_size(current_database())
            """)
            db_size, db_bytes = cur.fetchone()
            conn.close()
            lines = [f"PostgreSQL: {version}", f"Tamaño DB: {db_size}", "", "Tablas (por tamaño):"]
            for tname, tsize, _ in tables:
                lines.append(f"  {tname:<40} {tsize:>12}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error PostgreSQL: {exc}"

    # ── MySQL ───────────────────────────────────────────────────────────────────
    if driver in ("mysql", "mariadb"):
        if not _PYMYSQL_OK:
            return _MYSQL_NOT_AVAILABLE
        if not dsn:
            return "Error: 'dsn' requerido para MySQL."
        try:
            params = _parse_mysql_dsn(dsn)
            db     = params.get("database", "")
            conn   = pymysql.connect(**params, cursorclass=pymysql.cursors.Cursor)
            cur    = conn.cursor()
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute("""
                SELECT TABLE_NAME,
                       ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024, 1),
                       TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
            """, (db,))
            tables = cur.fetchall()
            conn.close()
            lines = [f"MySQL: {version}", f"Base de datos: {db}", "", "Tablas (por tamaño):"]
            for tname, tsize_kb, trows in tables:
                lines.append(f"  {tname:<40} {str(tsize_kb or 0):>8} KB  ~{trows or 0:,} filas")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error MySQL: {exc}"

    # ── SQLite (default) ────────────────────────────────────────────────────────
    conn, err = _sqlite_connect(db_path)
    if err:
        return err

    p = Path(db_path).expanduser()
    try:
        size_bytes = p.stat().st_size if p.exists() else 0
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        total_rows = 0
        table_stats = []
        for (tname,) in tables:
            try:
                cnt = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
                total_rows += cnt
                table_stats.append((tname, cnt))
            except Exception:
                table_stats.append((tname, "?"))

        page_size  = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist   = conn.execute("PRAGMA freelist_count").fetchone()[0]

        lines = [
            f"SQLite: {p}",
            f"Tamaño:        {size_bytes:,} bytes  ({size_bytes // 1024} KB)",
            f"Page size:     {page_size} bytes",
            f"Pages:         {page_count} total, {freelist} libres",
            f"Tablas:        {len(tables)}",
            f"Filas total:   {total_rows:,}",
            "",
            "Por tabla:",
        ]
        for tname, cnt in sorted(table_stats):
            lines.append(f"  {tname:<40} {str(cnt):>10}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


# ── Helpers de conexión unificados ────────────────────────────────────────────

def _pg_connect(dsn: str):
    if not _PSYCOPG2_OK:
        raise RuntimeError(_PG_NOT_AVAILABLE)
    return psycopg2.connect(dsn)


def _mysql_connect(dsn: str):
    if not _PYMYSQL_OK:
        raise RuntimeError(_MYSQL_NOT_AVAILABLE)
    params = _parse_mysql_dsn(dsn)
    return pymysql.connect(**params, cursorclass=pymysql.cursors.Cursor)


def _db_connect_any(driver: str, dsn: str = "", db_path: str = ""):
    """Devuelve (conn, kind) donde kind es 'sqlite'|'pg'|'mysql'."""
    d = driver.lower().strip() if driver else ""
    if d in ("sqlite", "sqlite3", "") and db_path:
        conn, err = _sqlite_connect(db_path)
        if err:
            raise RuntimeError(err)
        return conn, "sqlite"
    if d in ("postgresql", "postgres", "pg"):
        return _pg_connect(dsn), "pg"
    if d in ("mysql", "mariadb"):
        return _mysql_connect(dsn), "mysql"
    if not d and dsn:
        # Auto-detect from DSN prefix
        if dsn.startswith("postgresql") or dsn.startswith("postgres"):
            return _pg_connect(dsn), "pg"
        if dsn.startswith("mysql"):
            return _mysql_connect(dsn), "mysql"
    raise RuntimeError(
        f"Driver no identificado: '{driver}'. Usa: postgresql, mysql, sqlite. "
        "Para SQLite proporciona 'db_path'."
    )


def _get_schema_map(driver: str, dsn: str = "", db_path: str = "") -> dict:
    """Devuelve {table_name: [(col_name, col_type, nullable)]} para comparación."""
    d = driver.lower().strip() if driver else ""
    schema: dict[str, list] = {}

    if d in ("sqlite", "sqlite3", "") and db_path:
        conn, err = _sqlite_connect(db_path)
        if err:
            raise RuntimeError(err)
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
            for tbl in tables:
                info = conn.execute(f'PRAGMA table_info("{tbl}")').fetchall()
                schema[tbl] = [(r[1], r[2].upper(), "NO" if r[3] else "YES") for r in info]
        finally:
            conn.close()
        return schema

    if d in ("postgresql", "postgres", "pg"):
        if not _PSYCOPG2_OK:
            raise RuntimeError(_PG_NOT_AVAILABLE)
        conn = _pg_connect(dsn)
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        for tname, cname, dtype, nullable in cur.fetchall():
            schema.setdefault(tname, []).append((cname, dtype.upper(), nullable))
        conn.close()
        return schema

    if d in ("mysql", "mariadb"):
        if not _PYMYSQL_OK:
            raise RuntimeError(_MYSQL_NOT_AVAILABLE)
        conn = _mysql_connect(dsn)
        params = _parse_mysql_dsn(dsn)
        db = params.get("database", "")
        cur = conn.cursor()
        cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """, (db,))
        for tname, cname, dtype, nullable in cur.fetchall():
            schema.setdefault(tname, []).append((cname, dtype.upper(), nullable))
        conn.close()
        return schema

    raise RuntimeError(f"Driver desconocido: '{driver}'.")


# ── Nuevas herramientas unificadas ────────────────────────────────────────────

def _tool_db_connect(args: dict) -> str:
    """Prueba la conectividad a una base de datos PostgreSQL o MySQL.

    Args:
        driver (str): 'postgresql' o 'mysql'.
        dsn    (str): DSN de conexión.
    """
    import time
    driver = args.get("driver", "").lower().strip()
    dsn    = args.get("dsn", "")
    if not driver or not dsn:
        return "Error: 'driver' y 'dsn' requeridos (driver: postgresql | mysql)."

    t0 = time.time()
    try:
        if driver in ("postgresql", "postgres", "pg"):
            if not _PSYCOPG2_OK:
                return _PG_NOT_AVAILABLE
            conn = _pg_connect(dsn)
            cur  = conn.cursor()
            cur.execute("SELECT version(), current_database(), current_user, inet_server_addr(), inet_server_port()")
            version, db, user, host, port = cur.fetchone()
            conn.close()
            elapsed = time.time() - t0
            return (
                f"OK: conectado a PostgreSQL ({elapsed*1000:.0f} ms)\n"
                f"  Versión:  {version}\n"
                f"  Base:     {db}\n"
                f"  Usuario:  {user}\n"
                f"  Servidor: {host}:{port}"
            )

        if driver in ("mysql", "mariadb"):
            if not _PYMYSQL_OK:
                return _MYSQL_NOT_AVAILABLE
            conn = _mysql_connect(dsn)
            cur  = conn.cursor()
            cur.execute("SELECT VERSION(), DATABASE(), USER(), @@hostname")
            version, db, user, host = cur.fetchone()
            conn.close()
            elapsed = time.time() - t0
            return (
                f"OK: conectado a MySQL ({elapsed*1000:.0f} ms)\n"
                f"  Versión:  {version}\n"
                f"  Base:     {db}\n"
                f"  Usuario:  {user}\n"
                f"  Servidor: {host}"
            )

        return f"Error: driver '{driver}' desconocido. Usa: postgresql, mysql."
    except Exception as exc:
        return f"Error conectando ({driver}): {exc}"


def _tool_db_query(args: dict) -> str:
    """Ejecuta una query en PostgreSQL o MySQL y devuelve tabla ASCII.

    Args:
        driver (str): 'postgresql' o 'mysql'.
        dsn    (str): DSN de conexión.
        sql    (str): Sentencia SQL.
        params (list): Parámetros posicionales opcionales.
    """
    driver = args.get("driver", "").lower().strip()
    dsn    = args.get("dsn", "")
    sql    = args.get("sql", "").strip()
    params = args.get("params") or []

    if not dsn or not sql:
        return "Error: 'driver', 'dsn' y 'sql' requeridos."
    try:
        conn, kind = _db_connect_any(driver, dsn=dsn)
        if kind == "pg":
            cur = conn.cursor()
            cur.execute(sql, params or None)
            if cur.description is None:
                conn.commit()
                result = f"OK: {cur.rowcount} fila(s) afectada(s)."
            else:
                headers = [d[0] for d in cur.description]
                rows = cur.fetchmany(1000)
                result = _ascii_table(headers, rows)
                if len(rows) == 1000:
                    result += "\n[limitado a 1000 filas]"
        else:  # mysql
            cur = conn.cursor()
            cur.execute(sql, params or None)
            if cur.description is None:
                conn.commit()
                result = f"OK: {cur.rowcount} fila(s) afectada(s)."
            else:
                headers = [d[0] for d in cur.description]
                rows = cur.fetchmany(1000)
                result = _ascii_table(headers, rows)
                if len(rows) == 1000:
                    result += "\n[limitado a 1000 filas]"
        conn.close()
        return result
    except Exception as exc:
        return f"Error ({driver}): {exc}"


def _tool_db_schema(args: dict) -> str:
    """Muestra el esquema de tablas de una base de datos (columnas, tipos, nullable).

    Args:
        driver (str): 'postgresql', 'mysql' o 'sqlite'.
        dsn    (str): DSN para pg/mysql.
        db_path(str): Ruta para SQLite.
        schema (str): Schema a inspeccionar (PostgreSQL, default: 'public').
        table  (str): Tabla específica (vacío = todas).
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    dsn     = args.get("dsn", "")
    db_path = args.get("db_path", "")
    table   = args.get("table", "")

    try:
        schema_map = _get_schema_map(driver, dsn, db_path)
    except Exception as exc:
        return f"Error: {exc}"

    if table:
        schema_map = {k: v for k, v in schema_map.items() if k.lower() == table.lower()}
        if not schema_map:
            return f"Tabla '{table}' no encontrada."

    if not schema_map:
        return "(sin tablas)"

    lines = []
    for tbl, cols in sorted(schema_map.items()):
        lines.append(f"## {tbl}  ({len(cols)} columnas)")
        for cname, ctype, nullable in cols:
            null_str = "NULL" if nullable in ("YES", "YES", 1, True) else "NOT NULL"
            lines.append(f"  {cname:<35} {ctype:<20} {null_str}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _tool_db_tables(args: dict) -> str:
    """Lista las tablas de una base de datos con estadísticas de tamaño/filas.

    Args:
        driver (str): 'postgresql', 'mysql' o 'sqlite'.
        dsn    (str): DSN para pg/mysql.
        db_path(str): Ruta para SQLite.
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    dsn     = args.get("dsn", "")
    db_path = args.get("db_path", "")

    try:
        if driver in ("postgresql", "postgres", "pg"):
            if not _PSYCOPG2_OK:
                return _PG_NOT_AVAILABLE
            conn = _pg_connect(dsn)
            cur  = conn.cursor()
            cur.execute("""
                SELECT t.table_name,
                       pg_size_pretty(pg_total_relation_size(quote_ident(t.table_name))),
                       s.n_live_tup,
                       s.seq_scan,
                       s.idx_scan
                FROM information_schema.tables t
                LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
                WHERE t.table_schema = 'public'
                ORDER BY pg_total_relation_size(quote_ident(t.table_name)) DESC NULLS LAST
            """)
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return "(sin tablas)"
            lines = [f"{'Tabla':<40} {'Tamaño':>10} {'Filas':>10} {'Seq':>8} {'Idx':>8}"]
            lines.append("-" * 80)
            for tname, tsize, nrows, seq, idx in rows:
                lines.append(
                    f"{tname:<40} {(tsize or '?'):>10} {str(nrows or '?'):>10} "
                    f"{str(seq or 0):>8} {str(idx or 0):>8}"
                )
            return "\n".join(lines)

        if driver in ("mysql", "mariadb"):
            if not _PYMYSQL_OK:
                return _MYSQL_NOT_AVAILABLE
            params = _parse_mysql_dsn(dsn)
            db     = params.get("database", "")
            conn   = _mysql_connect(dsn)
            cur    = conn.cursor()
            cur.execute("""
                SELECT TABLE_NAME,
                       ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024, 1),
                       TABLE_ROWS,
                       ENGINE
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
            """, (db,))
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return "(sin tablas)"
            lines = [f"{'Tabla':<40} {'KB':>8} {'~Filas':>10} {'Motor':<10}"]
            lines.append("-" * 72)
            for tname, tkb, trows, engine in rows:
                lines.append(f"{tname:<40} {str(tkb or 0):>8} {str(trows or '?'):>10} {engine or '?':<10}")
            return "\n".join(lines)

        # SQLite
        conn, err = _sqlite_connect(db_path)
        if err:
            return err
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            if not tables:
                return "(sin tablas)"
            lines = [f"{'Tabla':<40} {'Filas':>8}"]
            lines.append("-" * 50)
            for (tname,) in tables:
                try:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
                except Exception:
                    cnt = "?"
                lines.append(f"{tname:<40} {str(cnt):>8}")
            return "\n".join(lines)
        finally:
            conn.close()
    except Exception as exc:
        return f"Error: {exc}"


def _tool_db_explain(args: dict) -> str:
    """Muestra el plan de ejecución de una query (EXPLAIN ANALYZE / EXPLAIN QUERY PLAN).

    Args:
        driver  (str): 'postgresql', 'mysql' o 'sqlite'.
        dsn     (str): DSN para pg/mysql.
        db_path (str): Ruta para SQLite.
        sql     (str): Sentencia SQL a analizar.
        analyze (bool): Para PostgreSQL: usar EXPLAIN ANALYZE (ejecuta la query). Default True.
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    dsn     = args.get("dsn", "")
    db_path = args.get("db_path", "")
    sql     = args.get("sql", "").strip()
    analyze = args.get("analyze", True)

    if not sql:
        return "Error: 'sql' requerido."

    try:
        if driver in ("postgresql", "postgres", "pg"):
            if not _PSYCOPG2_OK:
                return _PG_NOT_AVAILABLE
            prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)" if analyze else "EXPLAIN"
            conn = _pg_connect(dsn)
            cur  = conn.cursor()
            cur.execute(f"{prefix} {sql}")
            rows = cur.fetchall()
            conn.rollback()  # rollback si ANALYZE ejecutó DML
            conn.close()
            return "\n".join(r[0] for r in rows)

        if driver in ("mysql", "mariadb"):
            if not _PYMYSQL_OK:
                return _MYSQL_NOT_AVAILABLE
            conn = _mysql_connect(dsn)
            cur  = conn.cursor()
            cur.execute(f"EXPLAIN FORMAT=JSON {sql}")
            row = cur.fetchone()
            conn.close()
            if row:
                try:
                    import json as _json
                    return _json.dumps(_json.loads(row[0]), indent=2, ensure_ascii=False)
                except Exception:
                    return str(row[0])
            return "(sin plan)"

        # SQLite
        return _tool_sqlite_explain({"db_path": db_path, "sql": sql})
    except Exception as exc:
        return f"Error ({driver}): {exc}"


def _tool_db_export(args: dict) -> str:
    """Exporta datos de cualquier base de datos a CSV o JSON (fichero o stdout).

    Args:
        driver      (str):  'postgresql', 'mysql' o 'sqlite'.
        dsn         (str):  DSN para pg/mysql.
        db_path     (str):  Ruta para SQLite.
        sql         (str):  SELECT a ejecutar (alternativo a table).
        table       (str):  Nombre de tabla (genera SELECT * automáticamente).
        format      (str):  'csv' (default) o 'json'.
        output_path (str):  Ruta de fichero de salida (vacío = devuelve como texto).
    """
    driver      = args.get("driver", "sqlite").lower().strip()
    dsn         = args.get("dsn", "")
    db_path     = args.get("db_path", "")
    sql         = args.get("sql", "").strip()
    table       = args.get("table", "").strip()
    fmt         = args.get("format", "csv").lower()
    output_path = args.get("output_path", "").strip()

    if not sql and not table:
        return "Error: 'sql' o 'table' requerido."

    if not sql:
        sql = f'SELECT * FROM "{table}"'

    try:
        conn, kind = _db_connect_any(driver, dsn=dsn, db_path=db_path)
        if kind == "sqlite":
            cur = conn.execute(sql)
        else:
            cur = conn.cursor()
            cur.execute(sql)

        if (kind == "sqlite" and cur.description is None) or \
           (kind != "sqlite" and cur.description is None):
            conn.close()
            return "Error: la query no devuelve resultados (no es SELECT)."

        headers = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()

        if fmt == "json":
            data = [dict(zip(headers, [str(v) if v is not None else None for v in row]))
                    for row in rows]
            content = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(headers)
            writer.writerows([[str(v) if v is not None else "" for v in row] for row in rows])
            content = buf.getvalue()

        if output_path:
            out = Path(output_path).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content, encoding="utf-8")
            return f"OK: {len(rows)} fila(s) exportadas a '{output_path}' (formato {fmt})."
        return content
    except Exception as exc:
        return f"Error exportando: {exc}"


def _tool_db_import(args: dict) -> str:
    """Importa datos desde un fichero CSV/JSON a una tabla (bulk insert).

    Args:
        driver   (str):  'postgresql', 'mysql' o 'sqlite'.
        dsn      (str):  DSN para pg/mysql.
        db_path  (str):  Ruta para SQLite.
        table    (str):  Tabla de destino.
        file     (str):  Ruta a fichero CSV o JSON.
        data     (list): Array JSON de objetos (alternativo a file).
        mode     (str):  'insert' (default) o 'upsert' (INSERT OR REPLACE para SQLite,
                         INSERT ... ON CONFLICT DO NOTHING para pg).
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    dsn     = args.get("dsn", "")
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    file    = args.get("file", "").strip()
    data    = args.get("data")
    mode    = args.get("mode", "insert").lower()

    if not table:
        return "Error: 'table' requerido."

    # Cargar datos
    rows: list[dict] = []
    if data is not None:
        if not isinstance(data, list):
            return "Error: 'data' debe ser un array JSON de objetos."
        rows = [dict(r) for r in data if isinstance(r, dict)]
    elif file:
        p = Path(file).expanduser()
        if not p.exists():
            return f"Error: '{file}' no existe."
        if p.suffix.lower() == ".json":
            try:
                loaded = json.loads(p.read_text(encoding="utf-8"))
                rows = loaded if isinstance(loaded, list) else [loaded]
            except Exception as exc:
                return f"Error leyendo JSON: {exc}"
        else:
            try:
                with open(p, newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            except Exception as exc:
                return f"Error leyendo CSV: {exc}"
    else:
        return "Error: 'file' o 'data' requerido."

    if not rows:
        return "Error: sin filas a insertar."

    columns = list(rows[0].keys())

    try:
        conn, kind = _db_connect_any(driver, dsn=dsn, db_path=db_path)

        if kind == "sqlite":
            kw = "INSERT OR REPLACE" if mode == "upsert" else "INSERT"
            ph = ", ".join("?" for _ in columns)
            col_list = ", ".join(f'"{c}"' for c in columns)
            sql = f'{kw} INTO "{table}" ({col_list}) VALUES ({ph})'
            conn.executemany(sql, [[r.get(c, None) for c in columns] for r in rows])
            conn.commit()
            conn.close()

        elif kind == "pg":
            ph = ", ".join(f"%s" for _ in columns)
            col_list = ", ".join(f'"{c}"' for c in columns)
            if mode == "upsert":
                sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({ph}) ON CONFLICT DO NOTHING'
            else:
                sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({ph})'
            import psycopg2.extras as _pextras
            cur = conn.cursor()
            _pextras.execute_batch(cur, sql, [[r.get(c, None) for c in columns] for r in rows])
            conn.commit()
            conn.close()

        else:  # mysql
            ph = ", ".join("%s" for _ in columns)
            col_list = ", ".join(f"`{c}`" for c in columns)
            kw = "REPLACE" if mode == "upsert" else "INSERT"
            sql = f'{kw} INTO `{table}` ({col_list}) VALUES ({ph})'
            cur = conn.cursor()
            cur.executemany(sql, [[r.get(c, None) for c in columns] for r in rows])
            conn.commit()
            conn.close()

        return f"OK: {len(rows)} fila(s) importadas en '{table}' (modo {mode})."
    except Exception as exc:
        return f"Error importando: {exc}"


def _tool_db_migrate_check(args: dict) -> str:
    """Compara el esquema de dos bases de datos y devuelve las diferencias (tablas/columnas).

    Útil para detectar migraciones pendientes entre desarrollo y producción.

    Args:
        source_driver  (str): Driver de la fuente ('sqlite', 'postgresql', 'mysql').
        source_dsn     (str): DSN fuente (pg/mysql).
        source_db_path (str): Ruta fuente (sqlite).
        target_driver  (str): Driver del destino.
        target_dsn     (str): DSN destino.
        target_db_path (str): Ruta destino.
    """
    src_driver  = args.get("source_driver", "sqlite").lower().strip()
    src_dsn     = args.get("source_dsn", "")
    src_db_path = args.get("source_db_path", "")
    tgt_driver  = args.get("target_driver", "sqlite").lower().strip()
    tgt_dsn     = args.get("target_dsn", "")
    tgt_db_path = args.get("target_db_path", "")

    try:
        src = _get_schema_map(src_driver, src_dsn, src_db_path)
        tgt = _get_schema_map(tgt_driver, tgt_dsn, tgt_db_path)
    except Exception as exc:
        return f"Error obteniendo esquema: {exc}"

    src_tables = set(src.keys())
    tgt_tables = set(tgt.keys())

    lines = [f"Comparando esquemas: [{src_driver}] → [{tgt_driver}]", ""]

    added   = tgt_tables - src_tables
    removed = src_tables - tgt_tables
    common  = src_tables & tgt_tables

    if added:
        lines.append(f"Tablas NUEVAS en destino ({len(added)}):")
        for t in sorted(added):
            lines.append(f"  + {t}  ({len(tgt[t])} columnas)")
        lines.append("")

    if removed:
        lines.append(f"Tablas ELIMINADAS en destino ({len(removed)}):")
        for t in sorted(removed):
            lines.append(f"  - {t}  ({len(src[t])} columnas)")
        lines.append("")

    diffs = []
    for t in sorted(common):
        src_cols = {c[0]: c for c in src[t]}
        tgt_cols = {c[0]: c for c in tgt[t]}
        col_added   = set(tgt_cols) - set(src_cols)
        col_removed = set(src_cols) - set(tgt_cols)
        col_changed = {
            c for c in set(src_cols) & set(tgt_cols)
            if src_cols[c][1] != tgt_cols[c][1]
        }
        if col_added or col_removed or col_changed:
            diffs.append((t, col_added, col_removed, col_changed, src_cols, tgt_cols))

    if diffs:
        lines.append(f"Tablas con cambios de columnas ({len(diffs)}):")
        for t, col_added, col_removed, col_changed, src_cols, tgt_cols in diffs:
            lines.append(f"\n  ## {t}")
            for c in sorted(col_added):
                lines.append(f"    + {c}  ({tgt_cols[c][1]})")
            for c in sorted(col_removed):
                lines.append(f"    - {c}  ({src_cols[c][1]})")
            for c in sorted(col_changed):
                lines.append(f"    ~ {c}  {src_cols[c][1]} → {tgt_cols[c][1]}")

    if not added and not removed and not diffs:
        lines.append("Sin diferencias — esquemas idénticos.")

    return "\n".join(lines)


def _tool_db_indices(args: dict) -> str:
    """Lista los índices de una base de datos PostgreSQL o MySQL.

    Para SQLite usa sqlite_indices.

    Args:
        driver (str): 'postgresql', 'mysql' o 'sqlite'.
        dsn    (str): DSN para pg/mysql.
        db_path(str): Ruta para SQLite.
        table  (str): Tabla específica (vacío = todos los índices).
    """
    driver  = args.get("driver", "sqlite").lower().strip()
    dsn     = args.get("dsn", "")
    db_path = args.get("db_path", "")
    table   = args.get("table", "")

    try:
        if driver in ("postgresql", "postgres", "pg"):
            if not _PSYCOPG2_OK:
                return _PG_NOT_AVAILABLE
            conn = _pg_connect(dsn)
            cur  = conn.cursor()
            if table:
                cur.execute("""
                    SELECT indexname, indexdef, pg_size_pretty(pg_relation_size(indexrelid))
                    FROM pg_indexes
                    JOIN pg_class ON pg_class.relname = indexname
                    WHERE tablename = %s
                    ORDER BY indexname
                """, (table,))
            else:
                cur.execute("""
                    SELECT tablename, indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    ORDER BY tablename, indexname
                """)
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return "(sin índices)"
            lines = []
            if table:
                for iname, idef, isize in rows:
                    lines.append(f"{iname}  ({isize})\n  {idef}")
            else:
                cur_table = None
                for tname, iname, idef in rows:
                    if tname != cur_table:
                        lines.append(f"\n## {tname}")
                        cur_table = tname
                    lines.append(f"  {iname}: {idef}")
            return "\n".join(lines).strip()

        if driver in ("mysql", "mariadb"):
            if not _PYMYSQL_OK:
                return _MYSQL_NOT_AVAILABLE
            params = _parse_mysql_dsn(dsn)
            db     = params.get("database", "")
            conn   = _mysql_connect(dsn)
            cur    = conn.cursor()
            if table:
                cur.execute("""
                    SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, INDEX_TYPE
                    FROM INFORMATION_SCHEMA.STATISTICS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """, (db, table))
            else:
                cur.execute("""
                    SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, INDEX_TYPE
                    FROM INFORMATION_SCHEMA.STATISTICS
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
                """, (db,))
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return "(sin índices)"
            lines = []
            if table:
                cur_idx = None
                for iname, non_unique, seq, col, itype in rows:
                    if iname != cur_idx:
                        uniq = "" if non_unique else " [UNIQUE]"
                        lines.append(f"{iname}{uniq}  ({itype})")
                        cur_idx = iname
                    lines.append(f"  [{seq}] {col}")
            else:
                cur_tbl = None
                cur_idx = None
                for tname, iname, non_unique, col, itype in rows:
                    if tname != cur_tbl:
                        lines.append(f"\n## {tname}")
                        cur_tbl = tname
                        cur_idx = None
                    if iname != cur_idx:
                        uniq = "" if non_unique else " [UNIQUE]"
                        lines.append(f"  {iname}{uniq}  ({itype})")
                        cur_idx = iname
                    lines.append(f"    {col}")
            return "\n".join(lines).strip()

        # SQLite
        return _tool_sqlite_indices({"db_path": db_path, "table": table})
    except Exception as exc:
        return f"Error: {exc}"


# ── Nuevas herramientas SQLite ─────────────────────────────────────────────────

def _tool_sqlite_fts_search(args: dict) -> str:
    """Búsqueda full-text (FTS5) en una tabla virtual SQLite FTS.

    Si la tabla FTS no existe, la crea automáticamente indexando `content_table`.

    Args:
        db_path       (str):  Ruta al fichero .db.
        fts_table     (str):  Nombre de la tabla FTS5 (se crea si no existe).
        query         (str):  Expresión de búsqueda FTS5 (ej. 'python AND error').
        content_table (str):  Tabla de contenido original (para crear la FTS si no existe).
        content_col   (str):  Columna(s) a indexar, separadas por coma. Default: todas TEXT.
        limit         (int):  Máximo de resultados. Default: 20.
    """
    db_path       = args.get("db_path", "")
    fts_table     = args.get("fts_table", "")
    query         = args.get("query", "").strip()
    content_table = args.get("content_table", "")
    content_col   = args.get("content_col", "")
    limit         = int(args.get("limit", 20))

    if not fts_table or not query:
        return "Error: 'fts_table' y 'query' requeridos."

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        # ¿Existe ya la tabla FTS?
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (fts_table,)
        ).fetchone()

        if not exists:
            if not content_table:
                return (
                    f"Tabla FTS '{fts_table}' no existe. Proporciona 'content_table' "
                    "para crearla automáticamente."
                )
            # Obtener columnas TEXT de la content_table
            if content_col:
                cols = [c.strip() for c in content_col.split(",")]
            else:
                pragma = conn.execute(f'PRAGMA table_info("{content_table}")').fetchall()
                cols = [r[1] for r in pragma if "TEXT" in r[2].upper() or r[2] == ""]
                if not cols:
                    cols = [r[1] for r in pragma]
            col_list = ", ".join(cols)
            conn.execute(
                f'CREATE VIRTUAL TABLE "{fts_table}" USING fts5('
                f'{col_list}, content="{content_table}", content_rowid="rowid")'
            )
            conn.execute(f'INSERT INTO "{fts_table}"("{fts_table}") VALUES("rebuild")')
            conn.commit()

        rows = conn.execute(
            f'SELECT rowid, * FROM "{fts_table}" WHERE "{fts_table}" MATCH ? '
            f'ORDER BY rank LIMIT ?',
            (query, limit)
        ).fetchall()

        if not rows:
            return f"Sin resultados para '{query}'."

        cur = conn.execute(f'SELECT * FROM "{fts_table}" LIMIT 0')
        headers = ["rowid"] + [d[0] for d in cur.description]
        result = _ascii_table(headers, [tuple(r) for r in rows])
        return f"FTS5 '{fts_table}' — {len(rows)} resultado(s) para '{query}':\n\n{result}"
    except sqlite3.OperationalError as exc:
        if "fts5" in str(exc).lower():
            return "Error: SQLite no compilado con FTS5. Verifica tu versión de SQLite."
        return f"Error SQLite: {exc}"
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        conn.close()


def _tool_sqlite_bulk_insert(args: dict) -> str:
    """Inserta múltiples filas en una tabla SQLite desde un array JSON.

    Args:
        db_path (str):  Ruta al fichero .db.
        table   (str):  Nombre de la tabla.
        rows    (list): Array de objetos JSON [{col: val, ...}, ...].
        mode    (str):  'insert' (default) o 'upsert' (INSERT OR REPLACE).
    """
    db_path = args.get("db_path", "")
    table   = args.get("table", "")
    rows    = args.get("rows", [])
    mode    = args.get("mode", "insert").lower()

    if not table:
        return "Error: 'table' requerido."
    if not isinstance(rows, list) or not rows:
        return "Error: 'rows' debe ser un array JSON no vacío."

    columns = list(rows[0].keys())
    kw = "INSERT OR REPLACE" if mode == "upsert" else "INSERT"
    ph = ", ".join("?" for _ in columns)
    col_list = ", ".join(f'"{c}"' for c in columns)
    sql = f'{kw} INTO "{table}" ({col_list}) VALUES ({ph})'

    conn, err = _sqlite_connect(db_path)
    if err:
        return err
    try:
        conn.executemany(sql, [[r.get(c, None) for c in columns] for r in rows])
        conn.commit()
        return f"OK: {len(rows)} fila(s) insertadas en '{table}' (modo {mode})."
    except sqlite3.Error as exc:
        return f"Error SQLite: {exc}"
    finally:
        conn.close()


def _tool_sqlite_backup(args: dict) -> str:
    """Crea una copia de seguridad de una base de datos SQLite usando la API de backup.

    Args:
        db_path     (str): Ruta a la base de datos fuente.
        backup_path (str): Ruta del fichero de backup de destino.
    """
    db_path     = args.get("db_path", "")
    backup_path = args.get("backup_path", "")

    if not db_path or not backup_path:
        return "Error: 'db_path' y 'backup_path' requeridos."

    src  = Path(db_path).expanduser()
    dst  = Path(backup_path).expanduser()

    if not src.exists():
        return f"Error: '{db_path}' no existe."

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        conn_src = sqlite3.connect(str(src))
        conn_dst = sqlite3.connect(str(dst))
        conn_src.backup(conn_dst)
        conn_src.close()
        conn_dst.close()
        size = dst.stat().st_size
        return f"OK: backup completado → '{backup_path}'  ({size:,} bytes)."
    except Exception as exc:
        return f"Error: {exc}"


def _tool_mysql_explain(args: dict) -> str:
    """Muestra EXPLAIN FORMAT=JSON y el plan de ejecución de una query MySQL.

    Args:
        dsn      (str): DSN de conexión MySQL.
        sql      (str): Sentencia SQL a analizar.
        extended (bool): Usar EXPLAIN EXTENDED (columnas adicionales). Default False.
    """
    if not _PYMYSQL_OK:
        return _MYSQL_NOT_AVAILABLE
    dsn      = args.get("dsn", "")
    sql      = args.get("sql", "").strip()
    extended = args.get("extended", False)

    if not dsn or not sql:
        return "Error: 'dsn' y 'sql' requeridos."
    try:
        conn = _mysql_connect(dsn)
        cur  = conn.cursor()

        # EXPLAIN tabular
        prefix = "EXPLAIN EXTENDED" if extended else "EXPLAIN"
        cur.execute(f"{prefix} {sql}")
        headers = [d[0] for d in cur.description]
        rows    = cur.fetchall()
        table_out = _ascii_table(headers, rows)

        # EXPLAIN FORMAT=JSON
        cur.execute(f"EXPLAIN FORMAT=JSON {sql}")
        json_row = cur.fetchone()
        conn.close()

        json_out = ""
        if json_row:
            try:
                json_out = "\n\nFormato JSON:\n" + json.dumps(
                    json.loads(json_row[0]), indent=2, ensure_ascii=False
                )
            except Exception:
                json_out = f"\n\nFormato JSON:\n{json_row[0]}"

        return table_out + json_out
    except Exception as exc:
        return f"Error MySQL: {exc}"


def _tool_sql_format(args: dict) -> str:
    """Formatea una sentencia SQL con sangría de 4 espacios y palabras clave en mayúsculas.

    Args:
        sql (str): Sentencia SQL a formatear.
    """
    sql = args.get("sql", "").strip()
    if not sql:
        return "Error: 'sql' requerido."

    # Keywords que van en su propia línea (indent)
    INDENT_KEYWORDS = {"FROM", "WHERE", "JOIN", "LEFT JOIN", "RIGHT JOIN",
                       "INNER JOIN", "OUTER JOIN", "FULL JOIN", "CROSS JOIN",
                       "ON", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
                       "UNION", "UNION ALL", "INTERSECT", "EXCEPT"}
    # Keywords que siempre van en mayúsculas
    UPPER_KEYWORDS = INDENT_KEYWORDS | {
        "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
        "TABLE", "INDEX", "VIEW", "INTO", "VALUES", "SET", "AS", "AND", "OR",
        "NOT", "IN", "IS", "NULL", "DISTINCT", "EXISTS", "BETWEEN", "LIKE",
        "CASE", "WHEN", "THEN", "ELSE", "END", "ASC", "DESC", "PRIMARY", "KEY",
        "FOREIGN", "REFERENCES", "UNIQUE", "DEFAULT", "CONSTRAINT", "IF",
        "EXISTS", "WITH", "RETURNING",
    }

    import re
    # Tokenizar respetando strings
    tokens = re.findall(r"'[^']*'|\"[^\"]*\"|--[^\n]*|\S+", sql)

    result_parts = []
    indent = 0
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        tok_upper = tok.upper()
        # Combinar tokens de 2 palabras como LEFT JOIN
        if i + 1 < len(tokens):
            two = (tok_upper + " " + tokens[i+1].upper())
            if two in INDENT_KEYWORDS:
                tok = tok_upper + " " + tokens[i+1]
                tok_upper = two
                i += 1
        if tok_upper in INDENT_KEYWORDS:
            result_parts.append(f"\n    {tok_upper}")
        elif tok_upper in UPPER_KEYWORDS:
            result_parts.append(tok_upper)
        else:
            result_parts.append(tok)
        i += 1

    formatted = " ".join(result_parts).strip()
    # Cleanup: remove spaces before commas, after (
    formatted = re.sub(r"\s+,", ",", formatted)
    formatted = re.sub(r"\(\s+", "(", formatted)
    formatted = re.sub(r"\s+\)", ")", formatted)
    return formatted


# ── _TOOLS ────────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "sqlite_query",
        "description": "Ejecuta una query SQL en una base de datos SQLite y devuelve el resultado como tabla ASCII.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db de SQLite"},
                "sql":     {"type": "string", "description": "Sentencia SQL a ejecutar"},
                "params":  {"type": "array",  "description": "Parámetros posicionales opcionales"},
            },
            "required": ["db_path", "sql"],
        },
    },
    {
        "name": "sqlite_schema",
        "description": "Muestra el CREATE TABLE de todas las tablas de una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db de SQLite"},
            },
            "required": ["db_path"],
        },
    },
    {
        "name": "sqlite_tables",
        "description": "Lista las tablas de una base de datos SQLite con conteo de filas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db de SQLite"},
            },
            "required": ["db_path"],
        },
    },
    {
        "name": "sqlite_export",
        "description": "Exporta una tabla SQLite a CSV o JSON (devuelve el contenido como texto).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Nombre de la tabla"},
                "format":  {"type": "string", "description": "'csv' (default) o 'json'"},
            },
            "required": ["db_path", "table"],
        },
    },
    {
        "name": "sqlite_insert",
        "description": "Inserta una fila en una tabla SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Nombre de la tabla"},
                "data":    {"type": "object", "description": "Objeto JSON {columna: valor}"},
            },
            "required": ["db_path", "table", "data"],
        },
    },
    {
        "name": "sqlite_update",
        "description": "Actualiza filas en una tabla SQLite con WHERE obligatorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Nombre de la tabla"},
                "data":    {"type": "object", "description": "Objeto JSON {columna: valor}"},
                "where":   {"type": "string", "description": "Cláusula WHERE (sin WHERE), ej. \"id = 5\""},
            },
            "required": ["db_path", "table", "data", "where"],
        },
    },
    {
        "name": "sqlite_delete",
        "description": "Elimina filas de una tabla SQLite con WHERE obligatorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Nombre de la tabla"},
                "where":   {"type": "string", "description": "Cláusula WHERE (sin WHERE), ej. \"id = 5\""},
            },
            "required": ["db_path", "table", "where"],
        },
    },
    {
        "name": "sqlite_vacuum",
        "description": "Ejecuta VACUUM + ANALYZE en una base de datos SQLite para compactar y optimizar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
            },
            "required": ["db_path"],
        },
    },
    {
        "name": "sqlite_create_table",
        "description": "Ejecuta una sentencia CREATE TABLE en una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db (se crea si no existe)"},
                "sql":     {"type": "string", "description": "Sentencia CREATE TABLE completa"},
            },
            "required": ["db_path", "sql"],
        },
    },
    {
        "name": "sqlite_indices",
        "description": "Lista los índices de una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Tabla específica (vacío = todos los índices)"},
            },
            "required": ["db_path"],
        },
    },
    {
        "name": "sqlite_explain",
        "description": "Muestra el plan de ejecución (EXPLAIN QUERY PLAN) de una query SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "sql":     {"type": "string", "description": "Sentencia SQL a analizar"},
            },
            "required": ["db_path", "sql"],
        },
    },
    {
        "name": "pg_query",
        "description": "Ejecuta una query SELECT en PostgreSQL y devuelve tabla ASCII. Requiere psycopg2.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn": {"type": "string", "description": "DSN de conexión, ej. 'postgresql://user:pass@host/db'"},
                "sql": {"type": "string", "description": "Sentencia SQL a ejecutar"},
            },
            "required": ["dsn", "sql"],
        },
    },
    {
        "name": "pg_schema",
        "description": "Lista tablas y columnas del schema 'public' de una base de datos PostgreSQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn": {"type": "string", "description": "DSN de conexión PostgreSQL"},
            },
            "required": ["dsn"],
        },
    },
    {
        "name": "pg_explain",
        "description": "Muestra EXPLAIN ANALYZE de una query PostgreSQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn": {"type": "string", "description": "DSN de conexión PostgreSQL"},
                "sql": {"type": "string", "description": "Sentencia SQL a analizar"},
            },
            "required": ["dsn", "sql"],
        },
    },
    {
        "name": "mysql_query",
        "description": "Ejecuta una query SELECT en MySQL y devuelve tabla ASCII. Requiere pymysql.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn": {"type": "string", "description": "DSN de conexión, ej. 'mysql://user:pass@host/db'"},
                "sql": {"type": "string", "description": "Sentencia SQL a ejecutar"},
            },
            "required": ["dsn", "sql"],
        },
    },
    {
        "name": "mysql_schema",
        "description": "Lista tablas y columnas de una base de datos MySQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn": {"type": "string", "description": "DSN de conexión MySQL"},
            },
            "required": ["dsn"],
        },
    },
    {
        "name": "csv_to_sqlite",
        "description": "Importa un fichero CSV a una tabla de SQLite (crea la tabla automáticamente con columnas TEXT).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Ruta al fichero CSV"},
                "db_path":  {"type": "string", "description": "Ruta al fichero .db de SQLite (se crea si no existe)"},
                "table":    {"type": "string", "description": "Nombre de la tabla de destino"},
            },
            "required": ["csv_path", "db_path", "table"],
        },
    },
    {
        "name": "sqlite_to_csv",
        "description": "Exporta una tabla SQLite a un fichero CSV en disco.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path":     {"type": "string", "description": "Ruta al fichero .db"},
                "table":       {"type": "string", "description": "Nombre de la tabla"},
                "output_path": {"type": "string", "description": "Ruta del fichero CSV de salida"},
            },
            "required": ["db_path", "table", "output_path"],
        },
    },
    {
        "name": "db_stats",
        "description": "Estadísticas de base de datos: SQLite (tamaño/pages/filas), PostgreSQL (tamaño/tablas) o MySQL (tamaño/motor/filas).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db (SQLite)"},
                "driver":  {"type": "string", "description": "'sqlite' (default), 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para PostgreSQL o MySQL"},
            },
            "required": [],
        },
    },
    {
        "name": "sql_format",
        "description": "Formatea una sentencia SQL con palabras clave en mayúsculas e indentación estándar. No requiere dependencias.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "Sentencia SQL a formatear"},
            },
            "required": ["sql"],
        },
    },
    # ── Herramientas unificadas (db_*) ─────────────────────────────────────────
    {
        "name": "db_connect",
        "description": "Prueba la conectividad a PostgreSQL o MySQL y devuelve versión, usuario y servidor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver": {"type": "string", "description": "'postgresql' o 'mysql'"},
                "dsn":    {"type": "string", "description": "DSN de conexión"},
            },
            "required": ["driver", "dsn"],
        },
    },
    {
        "name": "db_query",
        "description": "Ejecuta una query SQL en PostgreSQL o MySQL y devuelve tabla ASCII.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver": {"type": "string", "description": "'postgresql' o 'mysql'"},
                "dsn":    {"type": "string", "description": "DSN de conexión"},
                "sql":    {"type": "string", "description": "Sentencia SQL a ejecutar"},
                "params": {"type": "array",  "description": "Parámetros posicionales opcionales"},
            },
            "required": ["driver", "dsn", "sql"],
        },
    },
    {
        "name": "db_schema",
        "description": "Muestra el esquema (columnas, tipos, nullable) de cualquier base de datos: SQLite, PostgreSQL o MySQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":  {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para pg/mysql"},
                "db_path": {"type": "string", "description": "Ruta para SQLite"},
                "table":   {"type": "string", "description": "Tabla específica (vacío = todas)"},
            },
            "required": [],
        },
    },
    {
        "name": "db_tables",
        "description": "Lista tablas con estadísticas (tamaño, filas, motor) para SQLite, PostgreSQL o MySQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":  {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para pg/mysql"},
                "db_path": {"type": "string", "description": "Ruta para SQLite"},
            },
            "required": [],
        },
    },
    {
        "name": "db_explain",
        "description": "Plan de ejecución unificado: EXPLAIN ANALYZE (PostgreSQL), EXPLAIN FORMAT=JSON (MySQL), EXPLAIN QUERY PLAN (SQLite).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":  {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para pg/mysql"},
                "db_path": {"type": "string", "description": "Ruta para SQLite"},
                "sql":     {"type": "string", "description": "Sentencia SQL a analizar"},
                "analyze": {"type": "boolean", "description": "Para PostgreSQL: usar EXPLAIN ANALYZE (default: true)"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "db_export",
        "description": "Exporta una tabla o query a CSV o JSON desde SQLite, PostgreSQL o MySQL. Opcionalmente guarda en fichero.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":      {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":         {"type": "string", "description": "DSN para pg/mysql"},
                "db_path":     {"type": "string", "description": "Ruta para SQLite"},
                "sql":         {"type": "string", "description": "SELECT a exportar (alternativo a table)"},
                "table":       {"type": "string", "description": "Tabla a exportar (genera SELECT *)"},
                "format":      {"type": "string", "description": "'csv' (default) o 'json'"},
                "output_path": {"type": "string", "description": "Ruta de salida (vacío = devuelve texto)"},
            },
            "required": [],
        },
    },
    {
        "name": "db_import",
        "description": "Importa datos de un fichero CSV/JSON o array inline a una tabla (bulk insert). Soporta SQLite, PostgreSQL y MySQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":  {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para pg/mysql"},
                "db_path": {"type": "string", "description": "Ruta para SQLite"},
                "table":   {"type": "string", "description": "Tabla de destino"},
                "file":    {"type": "string", "description": "Ruta a fichero CSV o JSON"},
                "data":    {"type": "array",  "description": "Array JSON de objetos (alternativo a file)"},
                "mode":    {"type": "string", "description": "'insert' (default) o 'upsert'"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "db_migrate_check",
        "description": "Compara el esquema de dos bases de datos y devuelve tablas/columnas añadidas, eliminadas o modificadas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_driver":  {"type": "string", "description": "Driver fuente: 'sqlite', 'postgresql', 'mysql'"},
                "source_dsn":     {"type": "string", "description": "DSN fuente (pg/mysql)"},
                "source_db_path": {"type": "string", "description": "Ruta fuente (sqlite)"},
                "target_driver":  {"type": "string", "description": "Driver destino"},
                "target_dsn":     {"type": "string", "description": "DSN destino"},
                "target_db_path": {"type": "string", "description": "Ruta destino"},
            },
            "required": ["source_driver", "target_driver"],
        },
    },
    {
        "name": "db_indices",
        "description": "Lista índices para SQLite, PostgreSQL (pg_indexes + tamaño) o MySQL (INFORMATION_SCHEMA.STATISTICS).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "driver":  {"type": "string", "description": "'sqlite', 'postgresql' o 'mysql'"},
                "dsn":     {"type": "string", "description": "DSN para pg/mysql"},
                "db_path": {"type": "string", "description": "Ruta para SQLite"},
                "table":   {"type": "string", "description": "Tabla específica (vacío = todos)"},
            },
            "required": [],
        },
    },
    # ── Nuevas herramientas SQLite ──────────────────────────────────────────────
    {
        "name": "sqlite_fts_search",
        "description": "Búsqueda full-text FTS5 en SQLite. Crea la tabla FTS automáticamente si no existe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path":       {"type": "string", "description": "Ruta al fichero .db"},
                "fts_table":     {"type": "string", "description": "Nombre de la tabla FTS5"},
                "query":         {"type": "string", "description": "Expresión FTS5, ej. 'python AND error'"},
                "content_table": {"type": "string", "description": "Tabla de contenido (para crear FTS si no existe)"},
                "content_col":   {"type": "string", "description": "Columnas a indexar separadas por coma"},
                "limit":         {"type": "integer","description": "Máximo de resultados (default: 20)"},
            },
            "required": ["db_path", "fts_table", "query"],
        },
    },
    {
        "name": "sqlite_bulk_insert",
        "description": "Inserta múltiples filas en una tabla SQLite desde un array JSON. Soporta modo upsert.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Ruta al fichero .db"},
                "table":   {"type": "string", "description": "Nombre de la tabla"},
                "rows":    {"type": "array",  "description": "Array de objetos JSON [{col: val, ...}]"},
                "mode":    {"type": "string", "description": "'insert' (default) o 'upsert' (INSERT OR REPLACE)"},
            },
            "required": ["db_path", "table", "rows"],
        },
    },
    {
        "name": "sqlite_backup",
        "description": "Crea una copia de seguridad de una base de datos SQLite usando la API de backup nativa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path":     {"type": "string", "description": "Ruta a la base de datos fuente"},
                "backup_path": {"type": "string", "description": "Ruta del fichero de backup de destino"},
            },
            "required": ["db_path", "backup_path"],
        },
    },
    {
        "name": "mysql_explain",
        "description": "Muestra el plan de ejecución de una query MySQL en formato tabular y JSON. Requiere pymysql.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dsn":      {"type": "string",  "description": "DSN de conexión MySQL"},
                "sql":      {"type": "string",  "description": "Sentencia SQL a analizar"},
                "extended": {"type": "boolean", "description": "Usar EXPLAIN EXTENDED (default: false)"},
            },
            "required": ["dsn", "sql"],
        },
    },
]

_TOOL_FNS = {
    # SQLite
    "sqlite_query":        _tool_sqlite_query,
    "sqlite_schema":       _tool_sqlite_schema,
    "sqlite_tables":       _tool_sqlite_tables,
    "sqlite_export":       _tool_sqlite_export,
    "sqlite_insert":       _tool_sqlite_insert,
    "sqlite_update":       _tool_sqlite_update,
    "sqlite_delete":       _tool_sqlite_delete,
    "sqlite_vacuum":       _tool_sqlite_vacuum,
    "sqlite_create_table": _tool_sqlite_create_table,
    "sqlite_indices":      _tool_sqlite_indices,
    "sqlite_explain":      _tool_sqlite_explain,
    "sqlite_fts_search":   _tool_sqlite_fts_search,
    "sqlite_bulk_insert":  _tool_sqlite_bulk_insert,
    "sqlite_backup":       _tool_sqlite_backup,
    # PostgreSQL
    "pg_query":            _tool_pg_query,
    "pg_schema":           _tool_pg_schema,
    "pg_explain":          _tool_pg_explain,
    # MySQL
    "mysql_query":         _tool_mysql_query,
    "mysql_schema":        _tool_mysql_schema,
    "mysql_explain":       _tool_mysql_explain,
    # Herramientas CSV/utilidades
    "csv_to_sqlite":       _tool_csv_to_sqlite,
    "sqlite_to_csv":       _tool_sqlite_to_csv,
    "db_stats":            _tool_db_stats,
    "sql_format":          _tool_sql_format,
    # Herramientas unificadas
    "db_connect":          _tool_db_connect,
    "db_query":            _tool_db_query,
    "db_schema":           _tool_db_schema,
    "db_tables":           _tool_db_tables,
    "db_explain":          _tool_db_explain,
    "db_export":           _tool_db_export,
    "db_import":           _tool_db_import,
    "db_migrate_check":    _tool_db_migrate_check,
    "db_indices":          _tool_db_indices,
}


# ── Prompts ───────────────────────────────────────────────────────────────────

_PROMPTS = {
    "schema_design": {
        "description": "Diseña un esquema de base de datos completo desde una descripción funcional",
        "arguments": [
            {"name": "description", "description": "Descripción del dominio: entidades, relaciones, casos de uso", "required": True},
            {"name": "engine",      "description": "Motor: sqlite, postgresql, mysql (default: postgresql)", "required": False},
            {"name": "style",       "description": "Estilo de salida: ddl, diagram, both (default: ddl)", "required": False},
        ],
    },
    "query_optimize": {
        "description": "Analiza una query lenta y propone optimizaciones con índices y reescrituras",
        "arguments": [
            {"name": "query",   "description": "Sentencia SQL a optimizar", "required": True},
            {"name": "schema",  "description": "DDL relevante (CREATE TABLE de las tablas implicadas)", "required": False},
            {"name": "explain", "description": "Salida de EXPLAIN ANALYZE o EXPLAIN QUERY PLAN", "required": False},
            {"name": "engine",  "description": "Motor: sqlite, postgresql, mysql (default: postgresql)", "required": False},
        ],
    },
    "migration_plan": {
        "description": "Genera el SQL de migración para pasar de un esquema fuente al destino",
        "arguments": [
            {"name": "source_schema", "description": "DDL actual (CREATE TABLE del esquema de origen)", "required": True},
            {"name": "target_schema", "description": "DDL objetivo (CREATE TABLE del nuevo esquema)", "required": False},
            {"name": "diff",          "description": "Salida de db_migrate_check (alternativo a schemas)", "required": False},
            {"name": "engine",        "description": "Motor: sqlite, postgresql, mysql (default: postgresql)", "required": False},
            {"name": "safe",          "description": "Solo operaciones seguras (no DROP, no NOT NULL sin default)", "required": False},
        ],
    },
}


def _prompt_get(name: str, arguments: dict) -> list[dict]:
    if name == "schema_design":
        description = arguments.get("description", "")
        engine      = arguments.get("engine", "postgresql")
        style       = arguments.get("style", "ddl")
        style_map   = {
            "ddl":     "DDL completo listo para ejecutar",
            "diagram": "diagrama ER en texto (notación ASCII o Mermaid)",
            "both":    "DDL + diagrama ER",
        }
        style_desc = style_map.get(style, style_map["ddl"])
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Diseña un esquema de base de datos {engine.upper()} para:\n\n{description}\n\n"
            f"Formato de salida: {style_desc}\n\n"
            "El esquema debe incluir:\n"
            "1. **Tablas** — con todos los campos, tipos de datos correctos para el motor, y comentarios\n"
            "2. **Claves primarias** — con estrategia (serial/UUID/autoincrement)\n"
            "3. **Claves foráneas** — con ON DELETE / ON UPDATE apropiados\n"
            "4. **Restricciones** — NOT NULL, UNIQUE, CHECK donde aplique\n"
            "5. **Índices** — para las consultas frecuentes más obvias\n"
            "6. **Decisiones de diseño** — por qué elegiste esta normalización, tipos y estrategias\n\n"
            f"Usa sintaxis válida para {engine.upper()}. Los nombres en snake_case."
        )}}]

    elif name == "query_optimize":
        query  = arguments.get("query", "")
        schema = arguments.get("schema", "")
        explain = arguments.get("explain", "")
        engine = arguments.get("engine", "postgresql")
        schema_str  = f"\n\nEsquema relevante:\n```sql\n{schema}\n```" if schema else ""
        explain_str = f"\n\nEXPLAIN output:\n```\n{explain}\n```" if explain else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Optimiza esta query {engine.upper()}:{schema_str}{explain_str}\n\n"
            f"```sql\n{query}\n```\n\n"
            "Analiza y proporciona:\n"
            "1. **Diagnóstico** — qué hace la query y dónde pierde rendimiento (full scan, sort, hash join…)\n"
            "2. **Índices recomendados** — CREATE INDEX exactos listos para ejecutar, con justificación\n"
            "3. **Reescritura** — versión optimizada de la query (si aplica), con explicación del cambio\n"
            "4. **Configuración** — parámetros del motor a ajustar si son relevantes (work_mem, innodb_buffer…)\n"
            "5. **Estimación de mejora** — orden de magnitud esperado (ej. '10x más rápido con el índice X')\n\n"
            "Si no hay suficiente información para diagnosticar, di exactamente qué necesitas."
        )}}]

    elif name == "migration_plan":
        source = arguments.get("source_schema", "")
        target = arguments.get("target_schema", "")
        diff   = arguments.get("diff", "")
        engine = arguments.get("engine", "postgresql")
        safe   = arguments.get("safe", False)
        input_str = ""
        if diff:
            input_str = f"\n\nDiferencias detectadas (db_migrate_check):\n```\n{diff}\n```"
        if source:
            input_str += f"\n\nEsquema origen:\n```sql\n{source}\n```"
        if target:
            input_str += f"\n\nEsquema destino:\n```sql\n{target}\n```"
        safe_note = "\n\nIMPORTANTE: solo operaciones SEGURAS (sin DROP TABLE/COLUMN, sin NOT NULL sin DEFAULT)." if safe else ""
        return [{"role": "user", "content": {"type": "text", "text": (
            f"Genera el SQL de migración {engine.upper()} para evolucionar el esquema:{input_str}{safe_note}\n\n"
            "Proporciona:\n"
            "1. **Script de migración** — SQL completo y ordenado, listo para ejecutar\n"
            "2. **Script de rollback** — SQL para deshacer la migración\n"
            "3. **Orden de ejecución** — explicación del orden y dependencias entre sentencias\n"
            "4. **Riesgos** — operaciones que bloquean tablas o pueden perder datos, con alternativas\n"
            "5. **Verificación** — queries para confirmar que la migración fue correcta\n\n"
            "Usa transacciones cuando sea posible. Marca con comentarios cada paso."
        )}}]

    else:
        return [{"role": "user", "content": {"type": "text", "text":
            f"Ejecuta el prompt '{name}' con: {json.dumps(arguments, ensure_ascii=False)}"
        }}]


# ── Recursos ─────────────────────────────────────────────────────────────────

def _resource_project_database() -> str:
    """Detecta y describe la configuración de bases de datos del proyecto."""
    root  = Path.cwd()
    parts = []

    # Ficheros SQLite
    sqlite_files = []
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        sqlite_files.extend(f for f in root.rglob(pattern)
                            if ".venv" not in str(f) and "__pycache__" not in str(f)
                            and ".git" not in str(f))
    if sqlite_files:
        parts.append("## Ficheros SQLite encontrados")
        for p in sorted(sqlite_files)[:10]:
            try:
                size = p.stat().st_size
                rel  = p.relative_to(root)
            except Exception:
                rel, size = p, 0
            parts.append(f"  {rel}  ({size:,} bytes)")

    # .env / config con DSN
    for env_file in (root / ".env", root / ".env.local", root / ".env.example",
                     root / "config" / "database.yml", root / "config" / "settings.py"):
        if env_file.exists():
            try:
                text = env_file.read_text(errors="replace")
                db_lines = [
                    ln.strip() for ln in text.splitlines()
                    if any(kw in ln.upper() for kw in
                           ("DATABASE_URL", "DB_URL", "DSN", "POSTGRES", "MYSQL",
                            "SQLALCHEMY", "DATABASE_URI"))
                    and "=" in ln and "#" not in ln.split("=")[0]
                ]
                if db_lines:
                    parts.append(f"\n## {env_file.name}")
                    for ln in db_lines[:8]:
                        # Ocultar contraseñas
                        import re
                        ln = re.sub(r'(:)[^:@/]+(@)', r'\1***\2', ln)
                        parts.append(f"  {ln}")
            except Exception:
                pass

    # Django settings
    for settings_path in root.rglob("settings.py"):
        if ".venv" in str(settings_path) or "__pycache__" in str(settings_path):
            continue
        try:
            text = settings_path.read_text(errors="replace")
            if "DATABASES" in text:
                start = text.find("DATABASES")
                snippet = text[start:start+400]
                parts.append(f"\n## Django DATABASES ({settings_path.relative_to(root)})")
                parts.append(f"```python\n{snippet}\n```")
                break
        except Exception:
            pass

    # Alembic
    for alembic_ini in root.rglob("alembic.ini"):
        if ".venv" in str(alembic_ini):
            continue
        try:
            text = alembic_ini.read_text(errors="replace")
            for ln in text.splitlines():
                if "sqlalchemy.url" in ln and "=" in ln:
                    import re
                    ln = re.sub(r'(:)[^:@/]+(@)', r'\1***\2', ln)
                    parts.append(f"\n## Alembic ({alembic_ini.relative_to(root)})")
                    parts.append(f"  {ln.strip()}")
                    break
        except Exception:
            pass

    if not parts:
        return (
            "(no se encontró configuración de base de datos en el directorio actual)\n"
            "Busca: ficheros .db/.sqlite, .env con DATABASE_URL, settings.py Django, alembic.ini"
        )
    return "\n".join(parts)


_RESOURCES = [
    {
        "uri":         "project://database",
        "name":        "Configuración de base de datos",
        "description": "Ficheros SQLite, DSN en .env, Django DATABASES, Alembic config del proyecto",
        "mimeType":    "text/plain",
    },
]

_RESOURCE_FNS = {
    "project://database": _resource_project_database,
}


def _handle(req: dict) -> None:
    method  = req.get("method", "")
    params  = req.get("params") or {}
    req_id  = req.get("id")

    if method == "initialize":
        _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
            "serverInfo": {"name": "database-assistant", "version": "2.0"},
        })

    elif method == "tools/list":
        _ok(req_id, {"tools": _TOOLS})

    elif method == "tools/call":
        name      = params.get("name", "")
        tool_args = params.get("arguments") or {}
        fn = _TOOL_FNS.get(name)
        if fn is None:
            _err(req_id, -32601, f"Tool desconocida: {name}")
            return
        try:
            result = fn(tool_args)
            _ok(req_id, {"content": [{"type": "text", "text": str(result)}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error en tool '{name}': {exc}")

    elif method == "prompts/list":
        _ok(req_id, {"prompts": [
            {"name": k, "description": v["description"], "arguments": v.get("arguments", [])}
            for k, v in _PROMPTS.items()
        ]})

    elif method == "prompts/get":
        name      = params.get("name", "")
        arguments = params.get("arguments") or {}
        messages  = _prompt_get(name, arguments)
        _ok(req_id, {"description": _PROMPTS.get(name, {}).get("description", name),
                     "messages": messages})

    elif method == "resources/list":
        _ok(req_id, {"resources": _RESOURCES})

    elif method == "resources/read":
        uri = params.get("uri", "")
        fn  = _RESOURCE_FNS.get(uri)
        if fn is None:
            _err(req_id, -32601, f"Recurso desconocido: {uri}")
            return
        try:
            content = fn()
            _ok(req_id, {"contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]})
        except Exception as exc:
            _err(req_id, -32603, f"Error leyendo recurso '{uri}': {exc}")

    elif req_id is not None:
        _err(req_id, -32601, f"Método desconocido: {method}")


def main() -> None:
    pg_status = "psycopg2 OK" if _PSYCOPG2_OK else "sin psycopg2"
    my_status = "pymysql OK" if _PYMYSQL_OK else "sin pymysql"
    sys.stderr.write(
        f"[database-assistant] MCP server v2.0 iniciado  "
        f"tools: {len(_TOOLS)}  prompts: {len(_PROMPTS)}  resources: {len(_RESOURCES)}"
        f"  {pg_status}  {my_status}\n"
    )
    sys.stderr.flush()
    while True:
        try:
            req = _recv()
            if req is None:
                break
            _handle(req)
        except (EOFError, BrokenPipeError):
            break
        except Exception as exc:
            sys.stderr.write(f"[database-assistant] Error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
