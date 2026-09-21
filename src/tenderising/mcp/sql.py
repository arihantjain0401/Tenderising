"""Read-only, constrained SQL execution for the `run_sql` MCP tool.

Safety: a read-only connection, SELECT/WITH/PRAGMA-table_info only, a blocked
verb list (defence-in-depth against stacked statements), and a row cap.
"""

from __future__ import annotations

import re
import sqlite3

from tenderising.config import DB_PATH, SQL_MAX_ROWS
from tenderising.db.models import Base

_BLOCKED = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "attach",
    "detach",
    "vacuum",
    "reindex",
    "replace",
    "grant",
    "revoke",
}


def schema_description() -> str:
    """Compact `table(col1, col2, ...)` listing for the LLM system prompt / tool description."""
    lines = []
    for name, table in sorted(Base.metadata.tables.items()):
        cols = ", ".join(c.name for c in table.columns)
        lines.append(f"{name}({cols})")
    return "\n".join(lines)


def is_read_only(sql: str) -> bool:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s)
    s = s.strip()
    if not s:
        return False
    up = s.upper()
    if not (up.startswith("SELECT") or up.startswith("WITH") or up.startswith("PRAGMA")):
        return False
    if up.startswith("PRAGMA") and not re.match(r"PRAGMA\s+TABLE_(INFO|XINFO)", up):
        return False
    tokens = set(re.findall(r"[a-z_]+", s.lower()))
    if tokens & _BLOCKED:
        return False
    return True


def run_sql(sql: str, max_rows: int = SQL_MAX_ROWS) -> dict:
    sql = sql.strip().rstrip(";").strip()
    if not is_read_only(sql):
        return {"error": "only read-only SELECT / WITH / PRAGMA table_info statements are allowed"}

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchmany(max_rows + 1)]
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]
        return {
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as exc:  # noqa: BLE001 - surface SQL errors to the model
        return {"error": f"SQL error: {exc!r}"}
    finally:
        con.close()
