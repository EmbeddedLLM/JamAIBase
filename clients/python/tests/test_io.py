from os.path import dirname, join, realpath
from re import escape
from tempfile import TemporaryDirectory

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


if __name__ == "__main__":
    test_yaml(TEST_DATA[1])
