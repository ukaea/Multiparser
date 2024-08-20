import re
import string
import tempfile
import time
import typing
import os.path
import importlib.util

import pytest
from conftest import fake_csv, fake_feather, fake_nml, fake_toml

import multiparser.parsing as mp_parse
from multiparser.parsing.file import (
    file_parser,
    record_csv as file_record_csv,
    record_fortran_nml,
    record_feather,
    record_toml,
)
from multiparser.parsing.tail import (
    record_with_delimiter,
    tail_file_n_bytes,
    record_csv as log_record_csv,
    _extract_label_value_pair,
)

DATA_LIBRARY: str = os.path.join(os.path.dirname(__file__), "data")


@pytest.mark.parsing
@pytest.mark.skipif(
    importlib.util.find_spec("f90nml") is None, reason="Module 'f90nml' not installed"
)
def test_parse_f90nml() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_nml(temp_d)
        _meta, _data = record_fortran_nml(input_file=_data_file)
        _, _data2 = mp_parse.record_file(_data_file, tracked_values=None, parser_func=None, file_type=None)
        assert "timestamp" in _meta
        assert list(sorted(_data.items())) == sorted(_data2.items())


@pytest.mark.parsing
def test_parse_csv() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_csv(temp_d)
        _meta, _data = file_record_csv(input_file=_data_file)
        _, _data2 = mp_parse.record_file(_data_file, tracked_values=None, parser_func=None, file_type=None)
        assert "timestamp" in _meta
        assert sorted([i.items() for i in _data]) == sorted([i.items() for i in _data2])


@pytest.mark.parsing
@pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None, reason="Module 'pyarrow' not installed"
)
def test_parse_feather() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_feather(temp_d)
        _meta, _ = record_feather(input_file=_data_file)
        assert "timestamp" in _meta


@pytest.mark.parsing
def test_parse_toml() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_toml(temp_d)
        _meta, _data = record_toml(input_file=_data_file)
        _, _data2 = mp_parse.record_file(_data_file, tracked_values=None, parser_func=None, file_type=None)
        assert "timestamp" in _meta
        assert list(sorted(_data.items())) == sorted(_data2.items())


@pytest.mark.parsing
def test_unrecognised_file_type() -> None:
    with tempfile.NamedTemporaryFile(suffix=".npy") as temp_f:
        with open(temp_f.name, "w") as out_f:
            out_f.write("...")
        with pytest.raises(TypeError):
            mp_parse.record_file(temp_f.name, tracked_values=None, parser_func=None, file_type=None)


@pytest.mark.parsing
def test_file_block_read() -> None:
    """Test that only the latest content is read from an appended to file"""
    with tempfile.NamedTemporaryFile(suffix=".log") as temp_f:
        with open(temp_f.name, "w") as out_f:
            for _ in range(8):
                out_f.write(f"{string.ascii_uppercase}\n")
        _bytes, _lines = tail_file_n_bytes(temp_f.name, None)
        assert _lines[-1] == f"{string.ascii_uppercase}\n"
        with open(temp_f.name, "a") as out_f:
            for _ in range(10):
                out_f.write(f"{string.ascii_lowercase}\n")
        _bytes, _lines = tail_file_n_bytes(temp_f.name, _bytes)
        assert f"{string.ascii_uppercase}\n" not in _lines
        assert _lines[-1] == f"{string.ascii_lowercase}\n"


@pytest.mark.parsing
@pytest.mark.parametrize(
    "fake_log",
    [(True, None), (False, None), (True, 2), (False, 2), (True, 3), (False, 3)],
    indirect=True,
    ids=(
        "labels-no_capture",
        "no_labels-no_capture",
        "labels-capture-2",
        "no_labels-capture-2",
        "labels-capture-3",
        "no_labels-capture-3",
    ),
)
def test_parse_log(fake_log, request) -> None:
    _fail_cases = ["no_labels-no_capture", "no_labels-capture-3", "labels-capture-3"]
    _id = request.node.name

    _file, _regex, _labels = fake_log.values()
    _regex_pairs = [(i, re.compile(j)) for i, j in zip(_labels, _regex)]
    if _id in [f"test_parse_log[{i}]" for i in _fail_cases]:
        with pytest.raises(ValueError):
            for _ in range(10):
                time.sleep(0.1)
                mp_parse.record_log(input_file=_file, tracked_values=_regex_pairs)
    else:
        for _ in range(10):
            time.sleep(0.1)
            mp_parse.record_log(input_file=_file, tracked_values=_regex_pairs)


@pytest.mark.parsing
@pytest.mark.parametrize(
    "fake_delimited_log",
    [(",", "csv"), (" ", "wsv")],
    indirect=True,
    ids=("comma", "whitespace"),
)
@pytest.mark.parametrize(
    "header", ([f"var_{i}" for i in range(5)], None), ids=("header", "no_header")
)
def test_parse_delimited(fake_delimited_log, request, header) -> None:
    _file = fake_delimited_log

    _, expected_output = request.node.get_closest_marker("parametrize").args

    with open(_file) as in_f:
        _all = in_f.readlines()
        if not header:
            _all = _all[1:]
    _collected = []

    for _ in range(10):
        time.sleep(0.1)
        _, _parsed_data  = mp_parse.record_log(
            input_file=_file,
            tracked_values=None,
            parser_func=record_with_delimiter,
            delimiter=expected_output[0][0],
            headers=header,
        )
        for i in _parsed_data:
            _collected += i

    assert all(i in _collected for i in _all)


@pytest.mark.parsing
@pytest.mark.parametrize(
    "fake_delimited_log",
    [(",", "csv")],
    indirect=True,
)
@pytest.mark.parametrize(
    "header",
    (["1231.235", "3455.223", "45632.234", "34536.23"], None),
    ids=("header", "no_header"),
)
@pytest.mark.parametrize(
    "convert", (True, False)
)
def test_tail_csv(fake_delimited_log, header, convert) -> None:
    _file = fake_delimited_log

    with open(_file) as in_f:
        _all = in_f.readlines()
        if not header:
            _all = _all[1:]
    _collected = []

    for _ in range(10):
        time.sleep(0.1)
        _, _parsed_data  = mp_parse.record_log(
            input_file=_file,
            convert=convert,
            tracked_values=None,
            parser_func=log_record_csv,
            headers=header,
        )
        for i in _parsed_data:
            _collected += i

    assert all(i in _collected for i in _all)


@pytest.mark.parsing
def test_flattening() -> None:
    assert mp_parse.flatten_data({"x": {"y": {"z": 2}}}) == {"x.y.z": 2}


@pytest.mark.parsing
@pytest.mark.parametrize(
    "regex_result", ("value", ("value",), ("value", "label"), ("value", "label", "surplus")),
    ids=("string_result", "single_result", "two_results", "three_results")
)
@pytest.mark.parametrize("label", (None, "label"), ids=("no_label", "label"))
def test_label_value_extraction(regex_result: tuple, label: str | None) -> None:

    if isinstance(regex_result, str) and not label:
        with pytest.raises(ValueError) as e:
            _extract_label_value_pair(
                regex_result,
                label=label,
                tracked_val=re.compile("undefined"),
                type_descriptor="NoType",
            )
            assert "must have an associated label" in str(e.value)
    elif isinstance(regex_result, tuple) and (
        (not label and len(regex_result) < 2) or len(regex_result) > 2
    ):
        with pytest.raises(ValueError) as e:
            _extract_label_value_pair(
                regex_result,
                label=label,
                tracked_val=re.compile("undefined"),
                type_descriptor="NoType",
            )
            assert "Expected label for regex with only single matching entry" in str(e.value)
    else:
        _extract_label_value_pair(
            regex_result,
            label=label,
            tracked_val=re.compile("undefined"),
            type_descriptor="NoType",
        )
