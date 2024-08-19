"""
Multiparser Full File Parsing
=============================

Contains functions and decorators for parsing file data as a whole.
The contents are sent to a dictionary.

"""

__date__ = "2023-10-16"
__author__ = "Kristian Zarebski"
__maintainer__ = "Kristian Zarebski"
__email__ = "kristian.zarebski@ukaea.uk"
__copyright__ = "Copyright 2024, United Kingdom Atomic Energy Authority"
import csv
import datetime
import functools
import json
import re
import os.path
import pickle
import platform
import typing

try:
    import f90nml
except ImportError:
    f90nml = None  # type: ignore

try:
    import flatdict
except ImportError:
    flatdict = None  # type: ignore

try:
    import pyarrow
except ImportError:
    pyarrow = None  # type: ignore

try:
    import pandas
except ImportError:
    pandas = None  # type: ignore

import loguru
import toml
import yaml

from multiparser.typing import TimeStampedData


def file_parser(parser: typing.Callable) -> typing.Callable:
    """Attach metadata to the current parser call for a file parser.

    This is a decorator for parser functions which attaches information
    on which file is being passed as well as the last modified time
    for that file.

    Parameters
    ----------
    parser : typing.Callable
        the parser function to wrap

    Returns
    -------
    typing.Callable
        new parse function with metadata capturing
    """

    @functools.wraps(parser)
    def _wrapper(input_file: str, *args, **kwargs) -> TimeStampedData:
        """Full file parser decorator"""
        _data: TimeStampedData = parser(input_file, *args, **kwargs)
        _meta_data: typing.Dict[str, str] = {
            "timestamp": datetime.datetime.fromtimestamp(
                os.path.getmtime(input_file)
            ).strftime("%Y-%m-%d %H:%M:%S.%f"),
            "hostname": platform.node(),
            "file_name": input_file,
        }
        return _meta_data | _data[0], _data[1]

    _wrapper.__name__ += "__mp_parser"

    return _wrapper


@file_parser
def record_json(input_file: str) -> TimeStampedData:
    """Parse a JSON file"""
    return {}, json.load(open(input_file))


@file_parser
def record_yaml(input_file: str) -> TimeStampedData:
    """Parse a YAML file"""
    return {}, yaml.load(open(input_file), Loader=yaml.SafeLoader)


@file_parser
def record_pickle(input_file: str) -> TimeStampedData:
    """Parse a pickle file"""
    return {}, pickle.load(open(input_file, "rb"))


@file_parser
def record_fortran_nml(input_file: str) -> TimeStampedData:
    """Parse a Fortran Named List"""
    if not f90nml:
        raise ImportError("Module 'f90nml' is required for Fortran named list")
    if not flatdict:
        raise ImportError("Module 'flatdict' is required for Fortran named list")

    return {}, dict(f90nml.read(input_file).todict())


@file_parser
def record_csv(input_file: str) -> TimeStampedData:
    """Parse a comma separated values file"""
    with open(input_file, newline="") as in_f:
        _read_csv = csv.DictReader(in_f)
        return {}, [row for row in _read_csv]


@file_parser
def record_feather(input_file: str) -> TimeStampedData:
    """Parse a feather file"""
    if not pyarrow:
        raise ImportError("Module 'pyarrow' is required for feather file type")
    if not pandas:
        raise ImportError("Module 'pandas' is required for feather file type")
    return {}, pandas.read_feather(input_file).to_dict()  # type: ignore


@file_parser
def record_parquet(input_file: str) -> TimeStampedData:
    """Parse a parquet file"""
    if not pyarrow:
        raise ImportError("Module 'pyarrow' is required for parquet file type")
    if not pandas:
        raise ImportError("Module 'pandas' is required for feather file type")
    return {}, pandas.read_parquet(input_file).to_dict()  # type: ignore


@file_parser
def record_toml(input_file: str) -> TimeStampedData:
    """Parse a TOML file"""
    return {}, toml.load(input_file)


SUFFIX_PARSERS: typing.Dict[typing.Tuple[str, ...], typing.Callable] = {
    ("csv",): record_csv,
    ("pkl", "pickle", "pckl"): record_pickle,
    ("pqt", "parquet"): record_parquet,
    ("toml",): record_toml,
    ("yaml", "yml"): record_yaml,
    ("nml", "fortran"): record_fortran_nml,
    ("json",): record_json,
    ("ft", "feather"): record_feather,
}


def _full_file_parse(parse_func, in_file, tracked_values, **parser_kwargs) -> TimeStampedData:
    """Apply specific parser to a file"""
    _data: typing.List[typing.Dict[str, typing.Any]]
    _meta: typing.Dict[str, typing.Any]
    _parsed = parse_func(input_file=in_file, **parser_kwargs)
    _meta, _data = _parsed

    # Need to handle case where there is only one set of values and
    # where there are multiple sets the same way
    if not isinstance(_data, (tuple, list, set)):
        _data = [_data]

    # If no tracked values are stated return everything
    if not tracked_values:
        return _parsed

    # Filter by key through each set of values
    _out_data: typing.List[typing.Dict[str, typing.Any]] = []

    for entry in _data:
        _out_data_entry: typing.Dict[str, typing.Any] = {}
        for tracked_val in tracked_values or []:
            _out_data_entry |= {
                k: v
                for k, v in entry.items()
                if (isinstance(tracked_val, str) and tracked_val in k)
                or (not isinstance(tracked_val, str) and tracked_val.findall(k))
            }
        _out_data.append(_out_data_entry)

    return _meta, _out_data


def record_file(
    input_file: str,
    *,
    tracked_values: typing.List[re.Pattern[str]] | None = None,
    parser_func: typing.Callable | None = None,
    file_type: str | None = None,
    **parser_kwargs
) -> TimeStampedData:
    """Record a recognised file, parsing its contents.

    If a parser exists for the given file type the file is read using
    the relevant parser and the results returned,

    Parameters
    ----------
    input_file : str
        the file to parse
    tracked_values : typing.List[re.Pattern[str]] | None
        regular expressions defining the values to be monitored, by default None
    parser_func : typing.Callable | None
        a custom parser to use for the given file
    file_type : str | None
        override the parser by file extension choice
    **parser_kwargs
        arguments to pass to a custom file parsing function if provided


    Returns
    -------
    TimeStampedData
        * metadata outlining properties such as modified time etc.
        * actual recorded data from the file.

    Raises
    ------
    TypeError
        if the given file type is not recognised
    """
    _extension: str = file_type or os.path.splitext(input_file)[1].replace(".", "")
    _tracked_vals: typing.List[re.Pattern[str]] | None = tracked_values or []

    if parser_func:
        return _full_file_parse(parser_func, input_file, _tracked_vals, **parser_kwargs)
    else:
        for key, parser in SUFFIX_PARSERS.items():
            if _extension not in key:
                continue
            return _full_file_parse(parser, input_file, _tracked_vals, **parser_kwargs)

    loguru.logger.error(
        f"The file extension '{_extension}' for file '{input_file}' is not supported for 'record_file' without custom parsing"
    )
    raise TypeError(f"File of type '{_extension}' could not be recognised")
