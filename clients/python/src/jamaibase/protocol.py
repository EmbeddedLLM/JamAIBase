from warnings import warn

from jamaibase.types import *  # noqa: F403

warn(
    "`jamaibase.protocol` is deprecated, use `jamaibase.types` instead.",
    FutureWarning,
    stacklevel=2,
)
