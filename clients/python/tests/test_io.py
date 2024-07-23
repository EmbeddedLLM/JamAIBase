from datetime import datetime
from os.path import dirname, join, realpath
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from jamaibase.utils import io

CURR_DIR = dirname(realpath(__file__))
TEST_DATA = [
    {},
    {"x": 9, "y": None, "z": {"a": "test", "b": [1, 2, 3]}},
]


@pytest.mark.parametrize("data", TEST_DATA)
def test_yaml(data):
    assert isinstance(data, dict)
    with TemporaryDirectory(dir=CURR_DIR) as staging_dir:
        assert io.read_yaml(io.dump_yaml(data, join(staging_dir, "test.yaml"))) == data


def test_yaml_validation():
    with pytest.raises((FileNotFoundError, ValueError)):
        io.read_yaml("x")


@pytest.mark.parametrize("data", TEST_DATA)
def test_json(data):
    assert isinstance(data, dict)
    assert io.json_loads(io.json_dumps(data)) == data
    with TemporaryDirectory(dir=CURR_DIR) as staging_dir:
        assert io.read_json(io.dump_json(data, join(staging_dir, "test.json"))) == data


def test_csv_to_df():
    data = 'ID,Updated at,col_0,col-1,col2\n06-0d,2024-07-12T06:07:49.711147+00:00,What is the fastest SSD?,"Title: ""Development of 1Tb 4b/cell""","Based"'
    df = io.csv_to_df(data)
    assert df.columns.tolist() == ["ID", "Updated at", "col_0", "col-1", "col2"]
    assert df.iloc[0].tolist() == [
        "06-0d",
        "2024-07-12T06:07:49.711147+00:00",
        "What is the fastest SSD?",
        'Title: "Development of 1Tb 4b/cell"',
        "Based",
    ]

    df = io.csv_to_df(data, column_names=["a", "b ", "c", "d", "e"])
    assert df.columns.tolist() == ["a", "b ", "c", "d", "e"]
    assert df.iloc[0].tolist() == [
        "ID",
        "Updated at",
        "col_0",
        "col-1",
        "col2",
    ]
    assert df.iloc[1].tolist() == [
        "06-0d",
        "2024-07-12T06:07:49.711147+00:00",
        "What is the fastest SSD?",
        'Title: "Development of 1Tb 4b/cell"',
        "Based",
    ]


def test_df_to_csv():
    with TemporaryDirectory() as tmp_dir:
        file_path = join(tmp_dir, "test_import_data_complete.csv")
        data = [
            {
                "ID": "06-0d",
                "Updated at": "2024-07-12T06:07:49.711147+00:00",
                "good": True,
                "words": 5,
                "stars": 0.0,
                "inputs": "",
                "summary": "",
            },
            {
                "ID": "06-1d",
                "Updated at": "2024-07-12T06:07:49.711147+00:00",
                "good": False,
                "words": 5,
                "stars": 1.0,
                "inputs": "我",
                "summary": "",
            },
            {
                "ID": "06-2d",
                "Updated at": "2024-07-12T06:07:49.711147+00:00",
                "good": True,
                "words": 5,
                "stars": 2.0,
                "inputs": '"Arrival" is a film',
                "summary": "",
            },
        ]
        dtypes = {
            "ID": "string",
            "Updated at": "datetime64[ns, UTC]",
            "good": "bool",
            "words": "int32",
            "stars": "float32",
            "inputs": "string",
            "summary": "string",
        }
        df = pd.DataFrame.from_dict(data).astype(dtypes)
        io.df_to_csv(df, file_path)
        with open(file_path, "r") as f:
            recreated_df = io.csv_to_df(f.read())
        assert (df == recreated_df).all(axis=None)


if __name__ == "__main__":
    test_df_to_csv()
