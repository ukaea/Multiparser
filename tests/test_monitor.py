import json
import logging
import os
import random
import re
import tempfile
import time
import typing

import pandas
import pytest
import pytest_mock
import toml
from conftest import fake_csv, fake_nml, fake_toml, to_nml

import multiparser
import multiparser.exceptions as mp_exc
import multiparser.thread as mp_thread


DATA_LIBRARY: str = os.path.join(os.path.dirname(__file__), "data")


@pytest.mark.monitor
@pytest.mark.parametrize(
    "exception",
    (
        "file_thread_exception",
        "file_monitor_thread_exception",
        "log_monitor_thread_exception",
        None,
    ),
)
def test_run_on_directory_all(
    fake_log, exception: str | None, mocker: pytest_mock.MockerFixture
) -> None:
    _interval: float = 0.1
    with tempfile.TemporaryDirectory() as temp_d:
        for _ in range(8):
            random.choice([fake_csv, fake_nml, fake_toml])(temp_d)

        def per_thread_callback(data, meta, exception=exception):
            if exception == "file_thread_exception":
                raise TypeError("Oh dear!")

        @mp_thread.abort_on_fail
        def fail_run(*_):
            raise AssertionError("Oh dear!")

        if exception in (
            "file_monitor_thread_exception",
            "log_monitor_thread_exception",
        ):
            mocker.patch.object(mp_thread.FileThreadLauncher, "run", fail_run)

        with multiparser.FileMonitor(
            per_thread_callback, interval=_interval, log_level=logging.DEBUG
        ) as monitor:
            monitor.track(os.path.join(temp_d, "*"))
            monitor.exclude(os.path.join(temp_d, "*.toml"))
            monitor.tail(*fake_log)
            monitor.run()
            for _ in range(10):
                time.sleep(_interval)
            if exception == "file_thread_exception":
                with pytest.raises(mp_exc.SessionFailure):
                    monitor.terminate()
            elif exception and exception != "file_thread_exception":
                with pytest.raises(AssertionError):
                    monitor.terminate()
            else:
                monitor.terminate()


@pytest.mark.monitor
def test_run_on_directory_filtered() -> None:
    _interval: float = 0.1
    with tempfile.TemporaryDirectory() as temp_d:
        _csv_dict = {
            "a_value": [10],
            "b_value": ["Hello World!"],
            "c_num": [5.6786],
            "d_other": [2.34],
        }
        _nml_dict = {"x_val_i": 4, "y": 3.45, "z_val_k": "testing"}
        _toml_dict = {"input_2": 2.34, "input_345": "test", "input_swe": 76}

        with open((_toml_file := os.path.join(temp_d, "toml_file.toml")), "w") as out_f:
            toml.dump(_toml_dict, out_f)
        pandas.DataFrame(_csv_dict).to_csv(
            (_csv_file := os.path.join(temp_d, "csv_file.csv"))
        )
        to_nml(_nml_dict, _nml_file := os.path.join(temp_d, "nml_file.nml"))

        def per_thread_callback(data, meta):
            print(
                json.dumps(
                    {
                        "time_recorded": meta["timestamp"],
                        "file": meta["file_name"],
                        "data": data,
                    },
                    indent=2,
                )
            )

        with multiparser.FileMonitor(
            per_thread_callback, interval=_interval
        ) as monitor:
            monitor.track(_csv_file, ["d_other", re.compile("\w_value")])
            monitor.track(_nml_file, [re.compile("\w_val_\w")])
            monitor.track(_toml_file, ["input_swe", re.compile(r"input_\d")])
            monitor.run()
            for _ in range(10):
                time.sleep(_interval)
            monitor.terminate()


@pytest.mark.parsing
@pytest.mark.parametrize(
    "stage,contains",
    [[1, ("matrix", "k", "v_sync", "i(1)", "i(2)")]],
    ids=[f"stage_{i}" for i in range(1, 2)],
)
def test_custom_data(stage: int, contains: typing.Tuple[str, ...]) -> None:
    _file: str = os.path.join(DATA_LIBRARY, f"custom_output_stage_{stage}.dat")

    def _custom_parser(
        file_name: str,
    ) -> typing.Tuple[typing.Dict[str, typing.Any], typing.Dict[str, typing.Any]]:
        _get_matrix = r"^[(\d+.\d+) *]{16}$"
        _initial_params_regex = r"^([\w_\(\)]+)\s*=\s*(\d+\.*\d*)$"
        _out_data = {}
        with open(file_name) as in_f:
            _file_data = in_f.read()
            _matrix_iter = re.finditer(_get_matrix, _file_data, re.MULTILINE)
            _init_params_iter = re.finditer(
                _initial_params_regex, _file_data, re.MULTILINE
            )

            _matrix = []
            for result in _matrix_iter:
                _matrix.append([float(i) for i in str(result.group()).split(" ")])
            _out_data["matrix"] = _matrix

            for result in _init_params_iter:
                _key = result.group(1)
                _value = result.group(2)
                _out_data[_key] = float(_value)

            if not _out_data:
                raise AssertionError("Failed to retrieve any values")

        return {}, _out_data

    _expected = {
        "matrix": [
            [10.0, 2.0, 3.0, 4.0],
            [2.0, 10.0, 2.5, 8.0],
            [3.0, 2.5, 10.0, 1.0],
            [4.0, 8.0, 1.0, 10.0],
        ],
        "k": 5.81,
        "v_sync": 4.2389,
        "i(1)": 3,
        "i(2)": 9.81,
    }

    def _validation_callback(data, _, check=contains):
        for key, value in _expected.items():
            if key in check:
                assert data[key] == value

    with multiparser.FileMonitor(
        _validation_callback, interval=0.1, log_level=logging.DEBUG
    ) as monitor:
        monitor.track(
            _file,
            custom_parser=_custom_parser,
            tracked_values=list(_expected.keys()),
            static=True,
        )
        monitor.run()
        time.sleep(2)
        monitor.terminate()
