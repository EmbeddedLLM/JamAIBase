from __future__ import annotations

import logging
import os
import pickle
import shutil
import subprocess
import traceback
from os.path import abspath, isdir, join, splitext
from pprint import pformat
from typing import Callable, Iterable

import numpy as np
import orjson
import srsly
import toml
from jamaibase.utils.types import JSONInput, JSONOutput
from PIL import ExifTags, Image

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
        **kwargs: Other keyword arguments to pass into `srsly.write_json`.

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


def read_file(path, rstrip: bool = True):
    with open(path, "r") as f:
        data = [line.rstrip() if rstrip else line for line in f.readlines()]
    return data


def dumps_file(string, path, utf8=True, lf_newline=True):
    encoding = "utf8" if utf8 else None
    newline = "\n" if lf_newline else None
    with open(path, "w", encoding=encoding, newline=newline) as f:
        f.write(string)
    return path


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


def listdir_full(path: str):
    return [join(path, directory) for directory in os.listdir(path)]


def subprocess_check_output(
    cmd: str, log_fn: Callable = logger.debug, **kwargs
) -> tuple[str, bool]:
    """A simple wrapper for `subprocess.check_output()`.

    The following arguments are set when calling `subprocess.check_output()`:
        - `shell = True`
        - `universal_newlines = True`
        - `stderr = subprocess.STDOUT`

    Args:
        cmd (str): Command to execute.
        log_fn (Callable, optional): A callable for logging. Defaults to `logger.debug`.

    Returns:
        outputs (str): Outputs from command execution (stdout and stderr).
        success (bool): True if no errors occurred.
    """
    try:
        outputs = subprocess.check_output(
            cmd,
            shell=True,
            universal_newlines=True,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        outputs = repr(e)
        success = False
    else:
        success = True
    log_fn(f"Command:\n'{cmd}'\nOutput:\n'{outputs.strip()}'")
    return outputs, success


def get_git_revision_hash(short: bool = True) -> str:
    # https://stackoverflow.com/a/66292983
    cmd = ["git", "rev-parse", "HEAD"]
    if short:
        cmd.insert(2, "--short")
    try:
        hash_val = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        hash_val = str(hash_val, "utf-8").strip()
    except subprocess.CalledProcessError as e:
        hash_val = "Unknown"
        logger.warning(
            f"Unable to get git revision hash, are you in a git directory? \n{e.output.decode('utf8')}"
        )
    return hash_val


def rmtree_if_exists(path: str):
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def rm_if_exists(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def find_files(
    directory: str,
    file_ext: Iterable[str],
    max_level: int = -1,
) -> list[str]:
    """
    Recursively lists all the files with matching extension(s) in a directory.

    Args:
        directory (str): The directory path.
        file_ext (Iterable[str]): A list of file extensions to search for.
        max_level (int, optional): Maximum recursion / directory depth. `max_level` < 0 implies no limit.
            Defaults to -1 (no limit).

    Raises:
        OSError: If `directory` is not a directory.

    Returns:
        matched_files (list[str]): A list of label file paths.
    """
    if not isinstance(file_ext, (list, tuple, set)):
        raise TypeError(
            f"`file_ext` must be one of (list, tuple, set), received: {type(file_ext)}"
        )
    file_ext = set(file_ext)

    def _match_file(file_path: str) -> bool:
        return splitext(file_path)[1] in file_ext

    if not isdir(directory):
        raise OSError(f"Not a directory: {directory}")

    directory = abspath(directory)
    matched_files = []
    for root, dirs, files in os.walk(directory, topdown=True):
        if max_level > 0 and root.count(os.sep) - directory.count(os.sep) > max_level:
            del dirs[:]
        else:
            dirs.sort()
            # Filter files
            files = [join(root, f) for f in sorted(files)]
            matched_files += filter(_match_file, files)
    return matched_files


def print_to_file(out: any, out_filepath: str):
    out = str(out)
    if out_filepath != "":
        with open(out_filepath, "a") as f:
            print(out, file=f)
    print(out)


def error_tb_mssg(
    e: Exception,
    name: str,
    log_vars: None | dict[str, any] = None,
) -> str:
    """Returns an error message with traceback for use with try...except.

    Args:
        e (Exception): The exception.
        name (str): Name of the process / program.
        log_vars (None | dict[str, any], optional): Variables to log. Defaults to None.

    Returns:
        message (str): Error message.
    """
    if log_vars is not None:
        log_vars = {
            k: (
                {"type": type(v), "shape": v.shape, "dtype": v.dtype}
                if isinstance(v, np.ndarray)
                else v
            )
            for k, v in log_vars.items()
        }
    mssg = (
        f"{name} encountered: {repr(e)}\n"
        f"Traceback: {''.join(traceback.format_tb(e.__traceback__))}"
    )
    return mssg + (f"vars: {pformat(log_vars)}\n" if log_vars is not None else "")
