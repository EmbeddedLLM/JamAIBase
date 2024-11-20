from datetime import timedelta
from os.path import join
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory

import lancedb

CURR_DIR = Path(__file__).resolve().parent


def test_lance():
    table_id = "test_table"
    with TemporaryDirectory() as tmp_dir:
        copytree(join(CURR_DIR, f"{table_id}.lance"), join(tmp_dir, f"{table_id}.lance"))
        lance_db = lancedb.connect(tmp_dir)
        # Try opening table
        table = lance_db.open_table(table_id)
        assert table.count_rows() > 0
        # Try deleting rows
        rows = table._dataset.to_table(offset=0, limit=100).to_pylist()
        row_ids = [r["ID"] for r in rows]
        for row_id in row_ids[3:]:
            table.delete(f"`ID` = '{row_id}'")
        # Try table optimization
        table.cleanup_old_versions(older_than=timedelta(seconds=0), delete_unverified=False)
        table.compact_files()


if __name__ == "__main__":
    test_lance()
