"""SQL pretty-printer for KPI Generator portal display."""

from __future__ import annotations

import re

_SQL_BREAK_KEYWORDS: tuple[str, ...] = (
    "UNION ALL",
    "UNION",
    "LEFT OUTER JOIN",
    "RIGHT OUTER JOIN",
    "FULL OUTER JOIN",
    "LEFT JOIN",
    "RIGHT JOIN",
    "INNER JOIN",
    "OUTER JOIN",
    "JOIN",
    "GROUP BY",
    "ORDER BY",
    "HAVING",
    "WHERE",
    "FROM",
)


def _split_sql_csv(expr: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in expr:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _format_select_list(text: str) -> str:
    match = re.match(
        r"^(SELECT\s+(?:DISTINCT\s+)?)(.+?)(\s+FROM\b.*)$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text
    prefix, columns_part, rest = match.groups()
    columns = _split_sql_csv(columns_part)
    if not columns:
        return text
    return prefix.rstrip() + "\n  " + ",\n  ".join(columns) + rest


def _format_group_order_list(text: str, keyword: str) -> str:
    pattern = re.compile(
        rf"(\b{keyword}\s+)(.+?)(?=\s+(?:{'|'.join(_SQL_BREAK_KEYWORDS)})\b|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return text
    prefix, columns_part = match.groups()
    columns = _split_sql_csv(columns_part.strip())
    if len(columns) <= 1:
        return text
    replacement = prefix + "\n  " + ",\n  ".join(columns)
    return text[: match.start()] + replacement + text[match.end() :]


def format_kpi_sql(sql: str) -> str:
    """Pretty-print KPI SQL with indented clauses and one projection per line."""
    text = re.sub(r"\s+", " ", sql.strip().rstrip(";"))
    if not text:
        return ""
    text = _format_select_list(text)
    text = _format_group_order_list(text, "GROUP BY")
    text = _format_group_order_list(text, "ORDER BY")
    for kw in _SQL_BREAK_KEYWORDS:
        pattern = re.compile(
            r"(?<!\w)" + kw.replace(" ", r"\s+") + r"(?=\s|$)",
            re.IGNORECASE,
        )
        text = pattern.sub("\n" + kw.upper(), text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        content = line.lstrip()
        upper = content.upper()
        if line.startswith("  "):
            lines.append(line)
        elif upper.startswith("AND ") or upper.startswith("OR "):
            lines.append(f"  {content}")
        else:
            lines.append(content)
    return "\n".join(lines)
