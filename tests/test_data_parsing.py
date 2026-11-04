import pathlib
import re
import string
import tempfile
import time
import os.path
import importlib.util

import pytest
from conftest import fake_csv, fake_feather, fake_nml, fake_parquet, fake_toml

import multiparser.parsing as mp_parse
from multiparser.parsing.file import (
    record_csv as file_record_csv,
    record_fortran_nml,
    record_feather,
    record_parquet,
    record_toml,
)
from multiparser.parsing.tail import (
    record_with_delimiter,
    tail_file_n_bytes,
    record_csv as log_record_csv,
    _extract_label_value_pair,
)

from multiparser.thread import _prepare_parsed_data, _reparse_action

DATA_LIBRARY: str = os.path.join(os.path.dirname(__file__), "data")


@pytest.mark.parsing
@pytest.mark.skipif(
    importlib.util.find_spec("f90nml") is None, reason="Module 'f90nml' not installed"
)
def test_parse_f90nml() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_nml(temp_d)
        _meta, _data = record_fortran_nml(input_file=_data_file)
        _, _data2 = mp_parse.record_file(
            _data_file, tracked_values=None, parser_func=None, file_type=None
        )
        assert "timestamp" in _meta
        assert list(sorted(_data.items())) == sorted(_data2.items())


@pytest.mark.parsing
def test_parse_csv() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_csv(temp_d)
        _meta, _data = file_record_csv(input_file=_data_file)
        _, _data2 = mp_parse.record_file(
            _data_file, tracked_values=None, parser_func=None, file_type=None
        )
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
@pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None, reason="Module 'pyarrow' not installed"
)
def test_parse_parquet() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_parquet(temp_d)
        _meta, _ = record_parquet(input_file=_data_file)
        assert "timestamp" in _meta


@pytest.mark.parsing
def test_parse_toml() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_toml(temp_d)
        _meta, _data = record_toml(input_file=_data_file)
        _, _data2 = mp_parse.record_file(
            _data_file, tracked_values=None, parser_func=None, file_type=None
        )
        assert "timestamp" in _meta
        assert list(sorted(_data.items())) == sorted(_data2.items())


@pytest.mark.parsing
def test_unrecognised_file_type() -> None:
    with tempfile.NamedTemporaryFile(suffix=".npy") as temp_f:
        with open(temp_f.name, "w") as out_f:
            out_f.write("...")
        with pytest.raises(TypeError):
            mp_parse.record_file(
                temp_f.name, tracked_values=None, parser_func=None, file_type=None
            )


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
    while not pathlib.Path(_file).exists():
        time.sleep(1)
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
        _metadata, _parsed_data = mp_parse.record_log(
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
@pytest.mark.parametrize("convert", (True, False))
def test_tail_csv(fake_delimited_log, header, convert) -> None:
    _file = fake_delimited_log

    with open(_file) as in_f:
        _all = in_f.readlines()
        if not header:
            _all = _all[1:]
    _collected = []

    for _ in range(10):
        time.sleep(0.1)
        _, _parsed_data = mp_parse.record_log(
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
    "regex_result",
    ("value", ("value",), ("value", "label"), ("value", "label", "surplus")),
    ids=("string_result", "single_result", "two_results", "three_results"),
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
            assert "Expected label for regex with only single matching entry" in str(
                e.value
            )
    else:
        _extract_label_value_pair(
            regex_result,
            label=label,
            tracked_val=re.compile("undefined"),
            type_descriptor="NoType",
        )


@pytest.mark.parsing
@pytest.mark.parametrize("parser", [log_record_csv, record_with_delimiter, None])
def test_callback_row_numbers_across_batches(tmp_path, parser):
    path = tmp_path / "data.csv"
    path.write_text("")
    captured = []
    metadata = {}
    kwargs = {"ignore_lines": [re.compile(r"^#")]}
    if parser is record_with_delimiter:
        kwargs["delimiter"] = ","

    def parse():
        nonlocal metadata
        metadata = _reparse_action(
            file_name=str(path),
            file_type=None,
            cached_metadata=metadata,
            modified_time="",
            tracked_vals=[("value", re.compile(r"^(\d+)$"))],
            parsing_callback=mp_parse.record_log,
            parser_kwargs=kwargs,
            cstm_parser=parser,
            lock=None,
            monitor_callback=lambda data, meta: captured.append((data, meta)),
            flatten_data=False,
        )

    parse()  # An initially empty file has no header yet.
    assert captured == []
    assert metadata["__rows_read"] == 0

    path.write_text("\n# ignored before header\n")
    parse()
    assert captured == []
    assert metadata["__rows_read"] == 0

    with path.open("a") as stream:
        stream.write("value\n\n10\n# ignored\n20\n\n")
    parse()
    assert [meta["row_number"] for _, meta in captured] == [0, 1]
    assert [data for data, _ in captured] == [{"value": 10}, {"value": 20}]
    assert metadata["__rows_read"] == 2
    assert "__read_bytes" in metadata
    assert isinstance(metadata["__rows_read"], int)

    # An ignored-only batch advances the byte cursor, not the line count.
    previous_bytes = metadata["__read_bytes"]
    with path.open("a") as stream:
        stream.write("# entirely ignored batch\n")
    parse()
    assert len(captured) == 2
    assert metadata["__rows_read"] == 2
    assert metadata["__read_bytes"] > previous_bytes

    # Ignored lines advance only the byte cursor; blank lines do not count either.
    with path.open("a") as stream:
        stream.write("# ignored again\n\n")
    parse()
    assert len(captured) == 2
    assert metadata["__rows_read"] == 2

    with path.open("a") as stream:
        stream.write("30\n\n40\n")
    parse()
    assert [meta["row_number"] for _, meta in captured] == [0, 1, 2, 3]
    assert captured[-1][0] == {"value": 40}
    assert metadata["__rows_read"] == 4
    # Each callback gets independent metadata, not an overwritten shared dict.
    assert captured[0][1]["row_number"] == 0

    parse()  # No new content must not repeat any rows or lose state.
    assert len(captured) == 4
    assert metadata["__rows_read"] == 4


@pytest.mark.parsing
@pytest.mark.parametrize("headers", [None, ["x", "y"]])
def test_direct_csv_parser_row_numbers(tmp_path, headers):
    path = tmp_path / "data.csv"
    path.write_text("x,y\n\n1,2\n3,4\n")
    parsed = log_record_csv(
        file_content=path.read_text(),
        headers=headers,
        __input_file=str(path),
        __read_bytes=path.stat().st_size,
    )
    assert isinstance(parsed[0]["__rows_read"], int)
    assert "__row_numbers" not in parsed[0]
    rows = [
        (meta["row_number"], data)
        for meta, data in _prepare_parsed_data(parsed)
        if data
    ]
    assert rows == [(0, {"x": 1, "y": 2}), (1, {"x": 3, "y": 4})]


@pytest.mark.parsing
@pytest.mark.parametrize("single_row", [False, True])
def test_custom_parser_numbers_returned_rows(tmp_path, single_row):
    path = tmp_path / "data.log"
    path.write_text("first\nsecond\n")

    def parser(file_content, **kwargs):
        row = {"block": file_content}
        return {"custom": "metadata"}, row if single_row else [{}, row, {}]

    metadata, data = mp_parse.record_log(str(path), parser_func=parser)
    assert metadata["__rows_read"] == 1
    assert metadata["__read_bytes"] == path.stat().st_size
    rows = [(meta, row) for meta, row in _prepare_parsed_data((metadata, data)) if row]
    assert len(rows) == 1
    assert rows[0][0]["row_number"] == 0
    assert rows[0][0]["custom"] == "metadata"

    with path.open("a") as stream:
        stream.write("third\nfourth\n")
    metadata, data = mp_parse.record_log(str(path), parser_func=parser, **metadata)
    rows = [(meta, row) for meta, row in _prepare_parsed_data((metadata, data)) if row]
    assert len(rows) == 1
    assert rows[0][0]["row_number"] == 1
    assert metadata["__rows_read"] == 2


@pytest.mark.parsing
@pytest.mark.parametrize("data", [{"x": 1}, [{"x": 1}, {"x": 2}], []])
def test_legacy_parser_return_formats(data):
    rows = list(_prepare_parsed_data(({"custom": "metadata"}, data)))
    expected = data if isinstance(data, list) else [data]
    assert rows == [({"custom": "metadata"}, row) for row in expected]
