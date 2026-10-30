"""
Multiparser Typing
==================

Defines typing aliases for multiparser argument types

"""

__date__ = "2023-10-16"
__author__ = "Kristian Zarebski"
__maintainer__ = "Kristian Zarebski"
__email__ = "kristian.zarebski@ukaea.uk"
__copyright__ = "Copyright 2024, United Kingdom Atomic Energy Authority"

import re
import typing

P = typing.ParamSpec("P")

PerThreadCallback = typing.Callable[
    [dict[str, typing.Any], dict[str, typing.Any]], None
]

MessageCallback = typing.Callable[[str], None]

ExceptionCallback = typing.Callable[[Exception], None]

TrackedValues = list[re.Pattern[str] | str] | re.Pattern[str] | str

TimeStampedData = tuple[
    dict[str, str | int | list[str]],
    dict[str, typing.Any] | list[dict[str, typing.Any]],
]

ParserFunction = typing.Callable[typing.Concatenate[str, P], TimeStampedData]

LogFileTrackable = dict[
    str,
    typing.AnyStr
    | list[tuple[str | None, re.Pattern[str]]]
    | bool
    | ParserFunction
    | dict[str, typing.Any]
    | None,
]

FullFileTrackable = dict[
    str,
    typing.AnyStr
    | bool
    | tuple[str | None, re.Pattern[str] | str]
    | ParserFunction
    | None
    | dict[str, typing.Any],
]

Trackable = LogFileTrackable | FullFileTrackable

TrackableList = list[LogFileTrackable] | list[FullFileTrackable]

TrackableType = typing.TypeVar("TrackableType")


class FullFileParsingCallback(typing.Protocol):
    def __call__(
        self,
        input_file: str,
        *,
        tracked_values: list[re.Pattern[str] | str] | None,
        parser_func: ParserFunction | None,
        file_type: str | None,
        **_,
    ) -> TimeStampedData: ...


class LogFileParsingCallback(typing.Protocol):
    def __call__(
        self,
        input_file: str,
        *,
        tracked_values: list[tuple[str | None, re.Pattern[str]]] | None = None,
        convert: bool = True,
        ignore_lines: list[re.Pattern[str] | str] | None = None,
        parser_func: ParserFunction | None = None,
        __read_bytes=None,  # type: ignore
        **parser_kwargs,
    ) -> TimeStampedData: ...


CallbackType = typing.TypeVar("CallbackType", bound=typing.Callable)
