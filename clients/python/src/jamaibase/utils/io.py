from __future__ import annotations

import csv
import logging
import pickle
from io import StringIO
from typing import Any

import numpy as np
import orjson
import pandas as pd
import srsly
import toml
from PIL import ExifTags, Image

from jamaibase.utils.types import JSONInput, JSONOutput

logger = logging.getLogger(__name__)


def load_pickle(file_path: str):
    with open(file_path, "rb") as f:
        return pickle.load(f)


def dump_pickle(out_path: str, obj: any):
    with open(out_path, "wb") as f:
        pickle.dump(obj, f)


def read_json(path: str) -> JSONOutput:
    """Reads a JSON file.

    Args:
        path (str): Path to the file.

    Returns:
        data (JSONOutput): The data.
    """
    with open(path, "r") as f:
        return orjson.loads(f.read())


def dump_json(data: JSONInput, path: str, **kwargs) -> str:
    """Writes a JSON file.

    Args:
        data (JSONInput): The data.
        path (str): Path to the file.
        **kwargs: Other keyword arguments to pass into `orjson.dumps`.

    Returns:
        path (str): Path to the file.
    """
    with open(path, "wb") as f:
        f.write(orjson.dumps(data, **kwargs))
    return path


def json_loads(data: str) -> JSONOutput:
    return orjson.loads(data)


def json_dumps(data: JSONInput) -> str:
    return orjson.dumps(data).decode("utf-8")


def read_yaml(path: str) -> JSONOutput:
    """Reads a YAML file.

    Args:
        path (str): Path to the file.

    Returns:
        data (JSONOutput): The data.
    """
    return srsly.read_yaml(path)


def dump_yaml(data: JSONInput, path: str, **kwargs) -> str:
    """Writes a YAML file.

    Args:
        data (JSONInput): The data.
        path (str): Path to the file.
        **kwargs: Other keyword arguments to pass into `srsly.write_yaml`.

    Returns:
        path (str): Path to the file.
    """
    srsly.write_yaml(path, data, **kwargs)
    return path


def read_toml(path: str) -> JSONOutput:
    """Reads a TOML file.

    Args:
        path (str): Path to the file.

    Returns:
        data (JSONOutput): The data.
    """
    with open(path, "r") as f:
        return toml.load(f)


def dump_toml(data: JSONInput, path: str, **kwargs) -> str:
    """Writes a TOML file.

    Args:
        data (JSONInput): The data.
        path (str): Path to the file.
        **kwargs: Other keyword arguments to pass into `toml.dump`.

    Returns:
        path (str): Path to the file.
    """
    with open(path, "w") as f:
        toml.dump(data, f)
    return path


def csv_to_df(
    data: str,
    column_names: list[str] | None = None,
    sep: str = ",",
    dtype: dict[str, Any] | None = None,
) -> pd.DataFrame:
    has_header = not (isinstance(column_names, list) and len(column_names) > 0)
    df = pd.read_csv(
        StringIO(data),
        header=0 if has_header else None,
        names=column_names,
        sep=sep,
        dtype=dtype,
    )
    return df


def df_to_csv(
    df: pd.DataFrame,
    file_path: str,
    sep: str = ",",
) -> None:
    df.to_csv(
        file_path,
        sep=sep,
        encoding="utf-8",
        lineterminator="\n",
        decimal=".",
        index=False,
        quoting=csv.QUOTE_NONNUMERIC,
        quotechar='"',
    )


def read_image(img_path: str) -> tuple[np.ndarray, bool]:
    """
    Reads an image file, and rotates the data according to its EXIF.

    Args:
        img_path (str): Image file path.

    Returns:
        image_array (np.ndarray): The image as a NumPy array of shape [H, W, C].
        is_rotated (bool): A boolean, True if the image is rotated.
    """
    with Image.open(img_path) as image:
        # exif = image.getexif().get_ifd(0x8769)
        exif = image.getexif()
        exif = {ExifTags.TAGS.get(tag_id, tag_id): exif.get(tag_id) for tag_id in exif}
        is_rotated = exif.get("Orientation") == 3
        if is_rotated:
            image = image.rotate(180)
        return np.asarray(image), is_rotated
