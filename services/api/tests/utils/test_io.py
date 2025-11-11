import pickle
import unittest
from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pandas as pd
from PIL import ExifTags, Image

from owl.utils.io import (
    csv_to_df,
    df_to_csv,
    dump_json,
    dump_pickle,
    dump_toml,
    dump_yaml,
    json_dumps,
    json_loads,
    load_pickle,
    read_image,
    read_json,
    read_toml,
    read_yaml,
)


class TestFileOperations(unittest.TestCase):
    def test_load_pickle(self):
        mock_data = {"key": "value"}
        with patch("builtins.open", mock_open(read_data=pickle.dumps(mock_data))):
            result = load_pickle("dummy_path")
            self.assertEqual(result, mock_data)

    def test_dump_pickle(self):
        mock_data = {"key": "value"}
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            dump_pickle("dummy_path", mock_data)
        mock_file().write.assert_called()

    def test_read_json(self):
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = read_json("dummy_path")
            self.assertEqual(result, {"key": "value"})

    def test_dump_json(self):
        mock_data = {"key": "value"}
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            result = dump_json(mock_data, "dummy_path")
            self.assertEqual(result, "dummy_path")
        mock_file().write.assert_called()

    def test_json_loads(self):
        mock_data = '{"key": "value"}'
        result = json_loads(mock_data)
        self.assertEqual(result, {"key": "value"})

    def test_json_dumps(self):
        mock_data = {"key": "value"}
        result = json_dumps(mock_data)
        self.assertEqual(result, '{"key":"value"}')

    def test_read_yaml(self):
        mock_data = "key: value"
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = read_yaml("dummy_path")
            self.assertEqual(result, {"key": "value"})

    def test_dump_yaml(self):
        mock_data = {"key": "value"}
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            result = dump_yaml(mock_data, "dummy_path")
            self.assertEqual(result, "dummy_path")
        mock_file().write.assert_called()

    def test_read_toml(self):
        mock_data = 'key = "value"'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            result = read_toml("dummy_path")
            self.assertEqual(result, {"key": "value"})

    def test_dump_toml(self):
        mock_data = {"key": "value"}
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            result = dump_toml(mock_data, "dummy_path")
            self.assertEqual(result, "dummy_path")
        mock_file().write.assert_called()

    def test_csv_to_df(self):
        mock_data = "col1,col2\n1,2\n3,4"
        result = csv_to_df(mock_data)
        expected = pd.DataFrame({"col1": [1, 3], "col2": [2, 4]})
        pd.testing.assert_frame_equal(result, expected)

    def test_csv_to_df_with_column_names(self):
        mock_data = "1,2\n3,4"
        result = csv_to_df(mock_data, column_names=["A", "B"])
        expected = pd.DataFrame({"A": [1, 3], "B": [2, 4]})
        pd.testing.assert_frame_equal(result, expected)

    @patch("pandas.DataFrame.to_csv")
    def test_df_to_csv(self, mock_to_csv):
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        df_to_csv(df, "dummy_path")
        mock_to_csv.assert_called_once()

    @patch("PIL.Image.open")
    def test_read_image_rotated(self, mock_open):
        mock_image = Image.new("RGB", (100, 100))
        mock_exif = {}
        for key, value in ExifTags.TAGS.items():
            if value == "Orientation":
                mock_exif[key] = 3  # 3 is the code for 180 degree rotation
                break
        mock_image.getexif = MagicMock(return_value=mock_exif)
        mock_open.return_value.__enter__.return_value = mock_image

        result, is_rotated = read_image("dummy_path")
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (100, 100, 3))
        self.assertTrue(is_rotated)

    @patch("PIL.Image.open")
    def test_read_image_not_rotated(self, mock_open):
        mock_image = Image.new("RGB", (100, 100))
        mock_exif = {}  # Empty EXIF data (no orientation)
        mock_image.getexif = MagicMock(return_value=mock_exif)
        mock_open.return_value.__enter__.return_value = mock_image

        result, is_rotated = read_image("dummy_path")
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (100, 100, 3))
        self.assertFalse(is_rotated)


if __name__ == "__main__":
    unittest.main()
