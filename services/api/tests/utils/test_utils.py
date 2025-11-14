import numpy as np
import pytest

from owl.utils import mask_content, mask_dict, merge_dict, validate_where_expr


def test_mask_content():
    # mask_content(x: str | list | dict | np.ndarray | Any) -> str | list | dict | None
    x = "str"
    assert mask_content(x) == "*** (str_len=3)"
    x = "long-string"
    assert mask_content(x) == "lo***ng (str_len=11)"
    x = 0
    assert mask_content(x) is None
    x = False
    assert mask_content(x) is None
    x = np.ones(3)
    assert mask_content(x) == "array(shape=(3,), dtype=float64)"
    x = ["long-string", np.ones(3), 0]
    assert mask_content(x) == ["lo***ng (str_len=11)", "array(shape=(3,), dtype=float64)", None]
    x = dict(x=["long-string", np.ones(3), 0], y=0, z=dict(a="str"))
    assert mask_content(x) == dict(
        x=["lo***ng (str_len=11)", "array(shape=(3,), dtype=float64)", None],
        y=None,
        z=dict(a="*** (str_len=3)"),
    )


def test_mask_dict():
    x = dict(a=0, b=1, c="", d="d")
    assert mask_dict(x) == dict(a=0, b="***", c="", d="***")


def test_merge_dict():
    x = dict(a=1, b=dict(p=2, q=3))
    y = dict(b=dict(p=30))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=30, q=3))

    x = dict(a=1, b=dict(p=2, q=3))
    y = dict(b=dict(p=[]))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=[], q=3))

    x = dict(a=1, b=[dict(p=2, q=3)])
    y = dict(b=[dict(p=30)])
    assert merge_dict(x, y) == dict(a=1, b=[dict(p=30)])

    x = dict(a=1, b=dict(p=dict(r=3, t=None), q=3))
    y = dict(b=dict(p=30))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=30, q=3))

    x = dict(a=1, b=dict(p=dict(r=3, t=None), q=3))
    y = dict(b=dict(p=dict(t=True)))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=dict(r=3, t=True), q=3))

    x = dict(a=1, b=dict(p=dict(r=3, t=None), q=3))
    y = dict(b=dict(p=dict(t={})))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=dict(r=3, t={}), q=3))

    x = dict(a=1, b=None)
    y = dict(b=dict(p=3))
    assert merge_dict(x, y) == dict(a=1, b=dict(p=3))

    x = dict(a=1, b=dict(p=2))
    y = dict(b=None)
    assert merge_dict(x, y) == dict(a=1, b=None)

    x = dict(a=1, b=dict(p=2, q=3))
    y = dict(b=dict(p=30), c=True)
    assert merge_dict(x, y) == dict(a=1, b=dict(p=30, q=3), c=True)

    x = dict(a=1, b=dict(p=2, q=3))
    y = dict(a="yes", b=dict(p=30), c=True)
    assert merge_dict(x, y) == dict(a="yes", b=dict(p=30, q=3), c=True)


def test_validate_where_expr():
    # Basic cases
    sql = validate_where_expr("WHERE a = 1")
    assert sql == "a = 1"
    sql = validate_where_expr("WHERE a =\n1")
    assert sql == "a = 1"
    sql = validate_where_expr("WHERE a = 'x'")
    assert sql == "a = 'x'"
    sql = validate_where_expr("WHERE (a = 'x')")
    assert sql == "(a = 'x')"
    sql = validate_where_expr("a = 1")
    assert sql == "a = 1"
    sql = validate_where_expr(""""a" = 'x'""")
    assert sql == """"a" = 'x'"""
    # Nested comparisons
    sql = validate_where_expr(
        """WHERE a = 1 OR ((b = NULL AND c = 9) OR ("b (1)" = TRUE) AND c = '9')"""
    )
    assert sql == """a = 1 OR ((b = NULL AND c = 9) OR ("b (1)" = TRUE) AND c = '9')"""
    # Comparison with a column
    sql = validate_where_expr('WHERE (("ID" = 1 AND "Updated at" = 9) AND "Updated at" = "M")')
    assert sql == '(("ID" = 1 AND "Updated at" = 9) AND "Updated at" = "M")'
    # Wildcard
    sql = validate_where_expr('"222 two three" ~* 3;')
    assert sql == '"222 two three" ~* 3'
    # Column name with parenthesis
    sql = validate_where_expr('"text (en)" ~* 3;')
    assert sql == '"text (en)" ~* 3'
    sql = validate_where_expr(""""text (en)" ~* 'yes (no)';""")
    assert sql == """"text (en)" ~* 'yes (no)'"""

    # ID mapping
    sql = validate_where_expr("WHERE a = 'x'", id_map={"a": "b"})
    assert sql == """"b" = 'x'"""
    sql = validate_where_expr(""""a" = 'x'""", id_map={"a": "b"})
    assert sql == """"b" = 'x'"""
    sql = validate_where_expr(
        """WHERE a = 1 OR ((b = NULL AND c = 9) OR ("b" = TRUE) AND c = '9')""",
        id_map={"a": "b"},
    )
    assert sql == """"b" = 1 OR (("b" = NULL AND "c" = 9) OR ("b" = TRUE) AND "c" = '9')"""
    sql = validate_where_expr(
        'WHERE (("ID" = 1 AND "Updated at" = 9) AND "Updated at" = "M")',
        id_map={"ID": "a", "Updated at": "b", "M": "c"},
    )
    assert sql == '(("a" = 1 AND "b" = 9) AND "b" = "c")'
    sql = validate_where_expr('"222 two three" ~* 3;', id_map={"222 two three": "a"})
    assert sql == '"a" ~* 3'

    # Illegal SQL
    for stmt in [
        # Classic drop table
        "DROP TABLE users; --",
        # Update data for all users
        "UPDATE users SET is_admin = 1",
        # Insert a new admin user
        "INSERT INTO users (username, is_admin) VALUES ('attacker', 1);",
        # Comment
        "email = 'a@a.com' --",
        "email = 'a@a.com' /*",
        # Shutdown the database (in some systems like SQL Server)
        "SHUTDOWN",
        # Attempt to alter a table
        "name = 'x' OR 1 = (ALTER TABLE users ADD COLUMN hacked VARCHAR(100))",
        "name = 'x' OR 1 = \n(ALTER TABLE users ADD COLUMN hacked VARCHAR(100))",
        "name = 'x' OR 1 = \r(ALTER TABLE users ADD COLUMN hacked VARCHAR(100))",
        # Keywords used directly
        "id > 0 OR UPDATE users SET is_admin = 1",
        "id = 1 OR MERGE INTO users",
        # Attempt to drop a column
        "ALTER TABLE users DROP COLUMN password_hash;",
        # Truncate a table
        "TRUNCATE TABLE logs;",
        # Functions
        "1=1 AND pg_sleep(10)",
        "1=1 AND pg_sleep (10)",
        "1=1 AND set_config(10)",
        "1=1 AND BENCHMARK(50000000, ENCODE('key', 'val'))",
        # Exec
        "EXEC master.dbo.xp_cmdshell 'dir c:';",
        # Using comments to break up keywords
        "DR/**/OP TABLE users;",
        # Using different character encodings or functions
        "EXEC(CHAR(100) + CHAR(114) + CHAR(111) + CHAR(112) + ' TABLE users')",  # SQL Server 'drop'
    ]:
        with pytest.raises(ValueError):
            validate_where_expr(stmt)
        with pytest.raises(ValueError):
            validate_where_expr(f"{stmt}; id = 1")
        sql = validate_where_expr(f"id = 1; {stmt}")
        assert sql == "id = 1"
