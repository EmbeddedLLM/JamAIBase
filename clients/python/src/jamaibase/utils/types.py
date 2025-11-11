import argparse
from enum import Enum
from typing import Callable, Type, TypeVar

from pydantic import BaseModel

try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, Enum):
        pass


### --- Enum Validator --- ###

E = TypeVar("E", bound=Enum)


def get_enum_validator(enum_cls: Type[E]) -> Callable[[str], E]:
    def _validator(v: str) -> E:
        try:
            return enum_cls[v]
        except KeyError:
            return enum_cls(v)

    return _validator


class CLI(BaseModel):
    @classmethod
    def parse_args(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        for field_name, field_info in cls.model_fields.items():
            field_type = field_info.annotation
            default = field_info.default
            description = field_info.description or ""
            if field_type is bool:
                parser.add_argument(
                    f"--{field_name}",
                    action="store_true",
                    help=description,
                )
            else:
                parser.add_argument(
                    f"--{field_name}",
                    type=field_type,
                    default=default,
                    required=default is ...,
                    help=description,
                )
        return cls(**vars(parser.parse_args()))
