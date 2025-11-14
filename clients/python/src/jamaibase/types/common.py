import unicodedata
from collections import OrderedDict
from datetime import timezone
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Dict, List, Tuple, Union

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field
from pydantic.types import AwareDatetime
from pydantic_extra_types.country import _index_by_alpha2 as iso_3166
from pydantic_extra_types.language_code import _index_by_alpha2 as iso_639

from jamaibase.utils.types import StrEnum

PositiveInt = Annotated[int, Field(ge=0, description="Positive integer.")]
PositiveNonZeroInt = Annotated[int, Field(gt=0, description="Positive non-zero integer.")]


def none_to_empty_string(v: str | None) -> str:
    if v is None:
        return ""
    return v


def empty_string_to_none(v: str | None) -> str | None:
    if not v:
        return None
    return v


NullableStr = Annotated[str | None, BeforeValidator(empty_string_to_none)]
EmptyIfNoneStr = Annotated[str, BeforeValidator(none_to_empty_string)]

EXAMPLE_CHAT_MODEL_IDS = ["openai/gpt-4o-mini"]
EXAMPLE_EMBEDDING_MODEL_IDS = [
    "openai/text-embedding-3-small-512",
    "ellm/sentence-transformers/all-MiniLM-L6-v2",
]
EXAMPLE_RERANKING_MODEL_IDS = [
    "cohere/rerank-multilingual-v3.0",
    "ellm/cross-encoder/ms-marco-TinyBERT-L-2",
]

# fmt: off
FilePath = Union[str, Path]
# Superficial JSON input/output types
# https://github.com/python/typing/issues/182#issuecomment-186684288
JSONOutput = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONOutputBin = Union[bytes, str, int, float, bool, None, Dict[str, Any], List[Any]]
# For input, we also accept tuples, ordered dicts etc.
JSONInput = Union[str, int, float, bool, None, Dict[str, Any], List[Any], Tuple[Any, ...], OrderedDict]
JSONInputBin = Union[bytes, str, int, float, bool, None, Dict[str, Any], List[Any], Tuple[Any, ...], OrderedDict]
YAMLInput = JSONInput
YAMLOutput = JSONOutput
# fmt: on


def _to_utc(d: AwareDatetime) -> AwareDatetime:
    return d.astimezone(timezone.utc)


DatetimeUTC = Annotated[AwareDatetime, AfterValidator(_to_utc)]

### --- String Validator --- ###


def _is_bad_char(char: str, *, allow_newline: bool) -> bool:
    """
    Checks if a character is disallowed.
    """
    # 1. Handle newlines based on the flag
    if char == "\n":
        return not allow_newline  # Bad if newlines are NOT allowed

    # 2. Check for other non-printable characters (like tabs, control codes)
    #    str.isprintable() is False for all non-printing chars except space.
    if not char.isprintable():
        return True

    # 3. Check for specific disallowed Unicode categories and blocks
    category = unicodedata.category(char)
    # Combining marks (e.g., for Zalgo text)
    if category.startswith("M"):
        return True
    # Box drawing
    if "\u2500" <= char <= "\u257f":
        return True
    # Block elements
    if "\u2580" <= char <= "\u259f":
        return True
    # Braille patterns
    if "\u2800" <= char <= "\u28ff":
        return True

    return False


def _str_pre_validator(
    value: Any, *, disallow_empty_string: bool = False, allow_newline: bool = False
) -> str:
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if disallow_empty_string and len(value) == 0:
        raise ValueError("Text is empty.")

    # --- Simplified and Consolidated Character Validation ---
    # The generator expression is efficient as `any()` will short-circuit
    # on the first bad character found.
    value = "".join(char for char in value if not unicodedata.category(char).startswith("M"))
    if any(_is_bad_char(char, allow_newline=allow_newline) for char in value):
        raise ValueError("Text contains disallowed or non-printable characters.")

    return value


SanitisedStr = Annotated[
    str,
    BeforeValidator(_str_pre_validator),
    # Cannot use Field here due to conflict with SQLModel
]
SanitisedMultilineStr = Annotated[
    str,
    BeforeValidator(partial(_str_pre_validator, disallow_empty_string=False, allow_newline=True)),
    # Cannot use Field here due to conflict with SQLModel
]
SanitisedNonEmptyStr = Annotated[
    str,
    BeforeValidator(partial(_str_pre_validator, disallow_empty_string=True)),
    # Cannot use Field here due to conflict with SQLModel
]
SanitisedNonEmptyMultilineStr = Annotated[
    str,
    BeforeValidator(partial(_str_pre_validator, disallow_empty_string=True, allow_newline=True)),
    # Cannot use Field here due to conflict with SQLModel
]

### --- Language Code Validator --- ###


WILDCARD_LANG_CODES = {"*", "mul"}
DEFAULT_MUL_LANGUAGES = [
    # ChatGPT supported languages
    # "sq",  # Albanian
    # "am",  # Amharic
    # "ar",  # Arabic
    # "hy",  # Armenian
    # "bn",  # Bengali
    # "bs",  # Bosnian
    # "bg",  # Bulgarian
    # "my",  # Burmese
    # "ca",  # Catalan
    "zh",  # Chinese
    # "hr",  # Croatian
    # "cs",  # Czech
    # "da",  # Danish
    # "nl",  # Dutch
    "en",  # English
    # "et",  # Estonian
    # "fi",  # Finnish
    "fr",  # French
    # "ka",  # Georgian
    # "de",  # German
    # "el",  # Greek
    # "gu",  # Gujarati
    # "hi",  # Hindi
    # "hu",  # Hungarian
    # "is",  # Icelandic
    # "id",  # Indonesian
    "it",  # Italian
    "ja",  # Japanese
    # "kn",  # Kannada
    # "kk",  # Kazakh
    "ko",  # Korean
    # "lv",  # Latvian
    # "lt",  # Lithuanian
    # "mk",  # Macedonian
    # "ms",  # Malay
    # "ml",  # Malayalam
    # "mr",  # Marathi
    # "mn",  # Mongolian
    # "no",  # Norwegian
    # "fa",  # Persian
    # "pl",  # Polish
    # "pt",  # Portuguese
    # "pa",  # Punjabi
    # "ro",  # Romanian
    # "ru",  # Russian
    # "sr",  # Serbian
    # "sk",  # Slovak
    # "sl",  # Slovenian
    # "so",  # Somali
    "es",  # Spanish
    # "sw",  # Swahili
    # "sv",  # Swedish
    # "tl",  # Tagalog
    # "ta",  # Tamil
    # "te",  # Telugu
    # "th",  # Thai
    # "tr",  # Turkish
    # "uk",  # Ukrainian
    # "ur",  # Urdu
    # "vi",  # Vietnamese
]


def _validate_lang(s: str) -> str:
    try:
        code = s.split("-")
        lang = code[0]
        lang = lang.lower().strip()
        if lang not in iso_639():
            raise ValueError
        if len(code) == 2:
            country = code[1]
            country = country.upper().strip()
            if country not in iso_3166():
                raise ValueError
            return f"{lang}-{country}"
        elif len(code) == 1:
            return lang
        else:
            raise ValueError
    except Exception as e:
        raise ValueError(
            f'Language code "{s}" is not ISO 639-1 alpha-2 or BCP-47 ([ISO 639-1 alpha-2]-[ISO 3166-1 alpha-2]).'
        ) from e


def _validate_lang_list(s: list[str]) -> list[str]:
    s = {lang.strip() for lang in s}
    if len(s & WILDCARD_LANG_CODES) > 0:
        s = list((s - WILDCARD_LANG_CODES) | set(DEFAULT_MUL_LANGUAGES))
    return [_validate_lang(lang) for lang in s]


LanguageCodeList = Annotated[list[str], AfterValidator(_validate_lang_list)]


class ProgressState(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Progress(BaseModel):
    key: str
    data: dict[str, Any] = {}
    state: ProgressState = ProgressState.STARTED
    error: str | None = None


class ProgressStage(BaseModel):
    name: str
    progress: int = 0


class TableImportProgress(Progress):
    load_data: ProgressStage = ProgressStage(name="Load data")
    parse_data: ProgressStage = ProgressStage(name="Parse data")
    upload_files: ProgressStage = ProgressStage(name="Upload files")
    add_rows: ProgressStage = ProgressStage(name="Add rows")
    index: ProgressStage = ProgressStage(name="Indexing")
