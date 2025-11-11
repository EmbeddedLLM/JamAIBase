import sqlparse
from loguru import logger
from sqlparse.sql import Comparison, Function, Identifier, Parenthesis, Where

from jamaibase.utils import (  # noqa: F401
    get_non_empty,
    get_ttl_hash,
    mask_content,
    mask_dict,
    mask_string,
    merge_dict,
    run,
    uuid7_draft2_str,
    uuid7_str,
)


def validate_where_expr(expr: str, *, id_map: dict[str, str] = None) -> str:
    sql = sqlparse.split(expr)[0]
    sql = sql.replace("\r", " ").replace("\n", " ").replace("\t", " ").strip().rstrip(";")
    if "shutdown" in sql.lower():
        raise ValueError("SQL expression contains shutdown.")
    if not sql:
        raise ValueError("SQL expression is empty.")
    tokens = sqlparse.parse(sql)[0].tokens
    if any(isinstance(t, Function) for t in tokens) > 0:
        raise ValueError(f"SQL expression contains function: `{expr}`")
    # Further breakdown Where
    if isinstance(tokens[0], Where):
        tokens = tokens[0].tokens[1:]
    token_types = []

    def _breakdown(_tokens):
        for t in _tokens:
            if t.ttype is None:
                _breakdown(t)
            else:
                token_types.append((str(t), list(t.ttype)))

    _breakdown(tokens)
    # logger.info(f"`{''.join(str(t) for t in tokens)}` {token_types=} {[type(t) for t in tokens]}")
    dml_tokens = [t for t in token_types if t[1][-1] == "DML"]
    ddl_tokens = [t for t in token_types if t[1][-1] == "DDL"]
    keyword_tokens = [
        t
        for t in token_types
        if t[1][0] == "Keyword" and t[0].lower() not in ["and", "or", "null", "true", "false"]
    ]
    comment_tokens = [t for t in token_types if t[1][0] == "Comment"]
    if len(dml_tokens) > 0:
        raise ValueError(f"SQL expression contains DML: `{expr}`")
    if len(ddl_tokens) > 0:
        raise ValueError(f"SQL expression contains DDL: `{expr}`")
    if len(keyword_tokens) > 0:
        raise ValueError(f"SQL expression contains keyword: `{expr}`")
    if len(comment_tokens) > 0 or "/*" in sql or "*/" in sql:
        raise ValueError(f"SQL expression contains comment: `{expr}`")
    if id_map:
        mapped_tokens = []

        def _map(_tokens):
            for t in _tokens:
                if isinstance(t, (Parenthesis, Comparison)):
                    _map(t)
                elif isinstance(t, Identifier):
                    t = str(t).strip('"')
                    t = id_map.get(t, t).strip('"')
                    mapped_tokens.append(f'"{id_map.get(t, t)}"')
                else:
                    mapped_tokens.append(t)

        _map(tokens)
    else:
        mapped_tokens = tokens
    new_sql = "".join(str(t) for t in mapped_tokens).strip().rstrip(";")
    logger.info(f"Validated SQL: `{expr}` -> `{new_sql}`")
    return new_sql
