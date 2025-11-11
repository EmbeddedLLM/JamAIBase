import csv
import logging
import pickle
from collections import OrderedDict
from io import StringIO
from mimetypes import guess_type
from os.path import splitext
from typing import Any

import filetype
import numpy as np
import orjson
import pandas as pd
import toml
import yaml
from PIL import ExifTags, Image

from jamaibase.types.common import JSONInput, JSONOutput

logger = logging.getLogger(__name__)

EMBED_WHITE_LIST = {
    "application/pdf": [".pdf"],
    "application/xml": [".xml"],
    "application/json": [".json"],
    "application/jsonl": [".jsonl"],
    "application/x-ndjson": [".jsonl"],
    "application/json-lines": [".jsonl"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "text/markdown": [".md"],
    "text/plain": [".txt"],
    "text/html": [".html"],
    "text/tab-separated-values": [".tsv"],
    "text/csv": [".csv"],
    "text/xml": [".xml"],
}
DOC_WHITE_LIST = EMBED_WHITE_LIST
IMAGE_WHITE_LIST = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
}
AUDIO_WHITE_LIST = {
    "audio/mpeg": [".mp3"],
    "audio/wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/x-pn-wav": [".wav"],
    "audio/wave": [".wav"],
    "audio/vnd.wav": [".wav"],
    "audio/vnd.wave": [".wav"],
}


def load_pickle(file_path: str):
    with open(file_path, "rb") as f:
        return pickle.load(f)


def dump_pickle(out_path: str, obj: Any):
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


def json_dumps(data: JSONInput, **kwargs) -> str:
    return orjson.dumps(data, **kwargs).decode("utf-8")


def read_yaml(path: str) -> JSONOutput:
    """Reads a YAML file.

    Args:
        path (str): Path to the file.

    Returns:
        data (JSONOutput): The data.
    """
    with open(path, "r") as f:
        return yaml.safe_load(f)


def dump_yaml(data: JSONInput, path: str, **kwargs) -> str:
    """Writes a YAML file.

    Args:
        data (JSONInput): The data.
        path (str): Path to the file.
        **kwargs: Other keyword arguments to pass into `yaml.dump`.

    Returns:
        path (str): Path to the file.
    """
    with open(path, "w") as f:
        yaml.dump(data, f, **kwargs)
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
    # Convert non-dictionary data into a dictionary
    if not isinstance(data, (dict, OrderedDict)):
        data = {"value": data}  # Wrap non-dictionary data in a dictionary

    with open(path, "w") as f:
        toml.dump(data, f)
    return path


def csv_to_df(
    data: str,
    column_names: list[str] | None = None,
    sep: str = ",",
    dtype: dict[str, Any] | None = None,
    **kwargs,
) -> pd.DataFrame:
    df = pd.read_csv(
        StringIO(data),
        names=column_names,
        sep=sep,
        dtype=dtype,
        **kwargs,
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
        header=True,
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


# Use the first MIME for each extension
MIME_WHITE_LIST = {**EMBED_WHITE_LIST, **IMAGE_WHITE_LIST, **AUDIO_WHITE_LIST}
EXT_TO_MIME = {}
for mime, exts in MIME_WHITE_LIST.items():
    for ext in exts:
        EXT_TO_MIME[ext] = EXT_TO_MIME.get(ext, mime)


def guess_mime(source: str | bytes) -> str:
    if isinstance(source, str):
        ext = splitext(source)[1].lower()
        mime = EXT_TO_MIME.get(ext, None)
        if mime is not None:
            return mime
    try:
        # `filetype` can handle file path and content bytes
        mime = filetype.guess(source)
        if mime is not None:
            return mime.mime
        if isinstance(source, str):
            # `mimetypes` can only handle file path
            mime, _ = guess_type(source)
            if mime is not None:
                return mime
            if source.endswith(".jsonl"):
                return "application/jsonl"
    except Exception:
        logger.warning(f'Failed to sniff MIME type of file "{source}".')
    return "application/octet-stream"
