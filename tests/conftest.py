import multiprocessing
import os
import random
import string
import tempfile
import time
import typing
import json
import yaml
import pickle
import pathlib

import pandas
import pytest
import toml
import xeger

XEGER_SEED: int = 0
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")


def rand_str(length: int = 5) -> str:
    _letters = list(string.ascii_letters)
    return "".join(random.choice(_letters) for _ in range(length))


def fake_csv(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str() + ".csv")
    pandas.DataFrame({rand_str(): [random.randint(0, 100) for _ in range(100)]}).to_csv(
        _file_name
    )
    return _file_name


def fake_feather(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str() + ".ft")
    pandas.DataFrame(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]}
    ).to_feather(_file_name)
    return _file_name


def fake_parquet(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str() + ".pqt")
    pandas.DataFrame(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]}
    ).to_parquet(_file_name)
    return _file_name


def fake_toml(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str()) + ".toml"
    toml.dump(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]},
        open(_file_name, "w"),
    )
    return _file_name


def fake_json(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str()) + ".json"
    json.dump(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]},
        open(_file_name, "w"),
    )
    return _file_name


def fake_yaml(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str()) + ".yml"
    yaml.dump(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]},
        open(_file_name, "w"),
    )
    return _file_name


def fake_pickle(output_dir: str, file_name: str | None = None) -> str:
    _file_name: str = file_name or os.path.join(output_dir, rand_str()) + ".pkl"
    pickle.dump(
        {rand_str(): [random.randint(0, 100) for _ in range(100)]},
        open(_file_name, "wb"),
    )
    return _file_name


def fake_nml(*_, **__) -> str:
    _file_name: str = os.path.join(DATA_DIR, "example.nml")
    return _file_name


def to_nml(dictionary: dict[str, typing.Any], file_name: str) -> None:
    with open(file_name, "w") as out_f:
        out_str = ["&DEMONML"]
        for key, value in dictionary.items():
            _value = value if not isinstance(value, str) else "'" + value + "'"
            out_str.append(f"{key.upper()}={_value}")
        out_str.append("/")
        out_f.write("\n".join(out_str))


@pytest.fixture
def fake_delimited_log(request) -> (
    typing.Generator[
        tuple[str, list[tuple[None, str]]], None, None
    ]
):
    _delimiter, _suffix = request.param

    _regex_gen = xeger.Xeger(limit=10, seed=XEGER_SEED)

    _gen_regex = r"\d+\.\d+"

    def _write_dummy_data(file_name: str) -> None:
        for _ in range(5):
            time.sleep(0.1)
            with open(file_name, "a") as out_f:
                _out_line = _delimiter.join([_regex_gen.xeger(_gen_regex) for _ in range(5)])
                out_f.writelines([_out_line])

    with tempfile.TemporaryDirectory() as temp_d:
        _file_name: str = os.path.join(temp_d, f"dummy.{_suffix}")
        pathlib.Path(_file_name).touch()
        _process = multiprocessing.Process(
            target=_write_dummy_data, args=(_file_name,)
        )
        _process.start()
        yield _file_name
        _process.join()


@pytest.fixture
def fake_log(request) -> (
    typing.Generator[
        tuple[str, list[tuple[None, str]]], None, None
    ]
):
    _labels, _capture_groups = request.param

    if _capture_groups == 2:
        _rand_regex_1 = r"(\w+_\w+_\d+)=(\d+)"
        _rand_regex_2 = r"(test_\w+)=(\'\w+\')"
    elif _capture_groups == 3:
        _rand_regex_1 = r"(\w+_)(\w+_\d+)=(\d+)"
        _rand_regex_2 = r"(test_)(\w+)=(\'\w+\')"
    else:
        _rand_regex_1 = r"\w+_\w+_\d+=(\d+)"
        _rand_regex_2 = r"test_\w+=(\'\w+\')"

    _regex_gen = xeger.Xeger(limit=10, seed=XEGER_SEED)

    def _write_dummy_data(file_name: str) -> None:
        for _ in range(5):
            time.sleep(0.1)
            with open(file_name, "a") as out_f:
                _out_line = _regex_gen.xeger(_rand_regex_1)
                _out_line += _regex_gen.xeger(r"\w+")
                _out_line += _regex_gen.xeger(_rand_regex_2)
                out_f.writelines([_out_line])

    with tempfile.TemporaryDirectory() as temp_d:
        _file_name: str = os.path.join(temp_d, "dummy.log")
        _process = multiprocessing.Process(
            target=_write_dummy_data, args=(_file_name,)
        )
        _process.start()
        time.sleep(0.1)
        yield {
            "path_glob_exprs": _file_name,
            "tracked_values": (_rand_regex_1, _rand_regex_2),
            "labels": ("var_1", "var_2") if _labels else (None, None)
        }
        _process.join()
