import json
import logging
import os
import random
import re
import tempfile
import time
import typing
import dataclasses

import pandas
import pytest
import pytest_mock
import multiprocessing
import toml
import xeger
from conftest import fake_csv, fake_nml, fake_toml, to_nml

import multiparser
import multiparser.exceptions as mp_exc
import multiparser.thread as mp_thread
import multiparser.parsing as mp_parse
from tests.conftest import fake_feather, fake_json, fake_parquet, fake_pickle, fake_yaml
from multiparser.parsing.tail import log_parser, record_with_delimiter as tail_record_delimited
from multiparser.parsing.file import file_parser


DATA_LIBRARY: str = os.path.join(os.path.dirname(__file__), "data")
XEGER_SEED: int = 10


@pytest.mark.monitor
@pytest.mark.parametrize(
    "fail", (True, False),
    ids=("fail", "pass")
)
def test_globex_check(fail: bool) -> None:
    if not fail:
        with multiparser.FileMonitor(
            lambda *_: None,
            log_level=logging.INFO,
            terminate_all_on_fail=True,
            timeout=2
        ) as monitor:
            monitor.track(
                path_glob_exprs=["files*"]
            )
    else:
        with pytest.raises(AssertionError):
            with multiparser.FileMonitor(
            lambda *_: None,
                log_level=logging.INFO,
                terminate_all_on_fail=True,
                timeout=2
            ) as monitor:
                monitor.track(
                    path_glob_exprs=[10]
                )

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
@pytest.mark.parametrize(
    "lock", (True, False),
    ids=("lock", "no_lock")
)
@pytest.mark.parametrize(
    "flatten", (True, False),
    ids=("flatten_data", "no_flatten")
)
@pytest.mark.parametrize(
    "fake_log", [
        (True, None)
    ],
    indirect=True,
)
def test_run_on_directory_all(
    fake_log, exception: str | None, mocker: pytest_mock.MockerFixture, lock: bool, flatten: bool
) -> None:
    _interval: float = 0.1
    _fakers: tuple[typing.Callable, ...] = (
        fake_csv,
        fake_nml,
        fake_toml,
        fake_feather,
        fake_json,
        fake_yaml,
        fake_pickle,
        fake_parquet
    )
    with tempfile.TemporaryDirectory() as temp_d:
        for faker in _fakers:
            faker(temp_d)
        for _ in range(8):
            random.choice(_fakers)(temp_d)

        def exception_callback(message: str) -> None:
            print(f"EXCEPTION: {message}")

        def notify_callback(message: str) -> None:
            print(f"NOTIFY: {message}")

        def per_thread_callback(_, __, exception=exception):
            if exception == "file_thread_exception":
                raise TypeError("Oh dear!")

        _allowed_exception = None

        if exception:
            if exception == "file_thread_exception":
                _allowed_exception = mp_exc.SessionFailure
            else:
                _allowed_exception = AssertionError

            with pytest.raises(_allowed_exception):
                with multiparser.FileMonitor(
                    per_thread_callback,
                    exception_callback=exception_callback,
                    notification_callback=notify_callback,
                    interval=_interval,
                    log_level=logging.INFO,
                    lock_callbacks=lock,
                    flatten_data=flatten,
                    terminate_all_on_fail=True
                ) as monitor:
                    monitor._file_thread_exception_test_case = exception == "file_monitor_thread_exception"
                    monitor._log_thread_exception_test_case = exception == "log_monitor_thread_exception"
                    monitor.track(path_glob_exprs=os.path.join(temp_d, "*"))
                    monitor.exclude(os.path.join(temp_d, "*.toml"))
                    monitor.tail(**fake_log)
                    monitor.run()
                    for _ in range(10):
                        time.sleep(_interval)
                    monitor.terminate()
        else:
            with multiparser.FileMonitor(
                per_thread_callback,
                interval=_interval,
                log_level=logging.INFO,
                terminate_all_on_fail=True
            ) as monitor:
                monitor.track(path_glob_exprs=os.path.join(temp_d, "*"))
                monitor.exclude(os.path.join(temp_d, "*.toml"))
                monitor.tail(**fake_log)
                monitor.run()
                for _ in range(10):
                    time.sleep(_interval)
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
            per_thread_callback,
            interval=_interval,
            flatten_data=True,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.track(path_glob_exprs=_csv_file, tracked_values=["d_other", re.compile("\w_value")])
            monitor.track(path_glob_exprs=_nml_file, tracked_values=[re.compile("\w_val_\w")])
            monitor.track(path_glob_exprs=_toml_file, tracked_values=["input_swe", re.compile(r"input_\d")])
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
def test_custom_data(stage: int, contains: tuple[str, ...]) -> None:
    _file: str = os.path.join(DATA_LIBRARY, f"custom_output_stage_{stage}.dat")

    @mp_parse.file_parser
    def _parser_func(
        input_file: str,
        **_
    ) -> tuple[dict[str, typing.Any], dict[str, typing.Any]]:
        _get_matrix = r"^[(\d+.\d+) *]{16}$"
        _initial_params_regex = r"^([\w_\(\)]+)\s*=\s*(\d+\.*\d*)$"
        _out_data = {}
        with open(input_file) as in_f:
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
        _validation_callback,
        interval=0.1,
        log_level=logging.DEBUG,
        terminate_all_on_fail=True
    ) as monitor:
        monitor.track(
            path_glob_exprs=_file,
            parser_func=_parser_func,
            tracked_values=list(_expected.keys()),
            static=True,
        )
        monitor.run()
        time.sleep(2)
        monitor.terminate()


@pytest.mark.parsing
def test_parse_log_in_blocks() -> None:
    _refresh_interval: float = 0.1
    _expected = [{f"var_{i}": random.random() * 10 for i in range(5)} for _ in range(10)]
    _xeger = xeger.Xeger(seed=XEGER_SEED)
    _file_blocks = []
    _gen_ignore_pattern = r"<!--ignore-this-\w+-\d+-->"
    _gen_rgx = r"\w+: \d+\.\d+"
    _file_blocks += [
        [_xeger.xeger(_gen_rgx)+"\n"] +
        [_xeger.xeger(_gen_rgx)+ "\n"] +
        [_xeger.xeger(_gen_rgx)+"\n"] +
        [_xeger.xeger(_gen_rgx)+"\n"] +
        [_xeger.xeger(_gen_ignore_pattern)+"\n"] +
        ["\tData Out\n"] +
        [f"\tResult: {i['var_0']}\n"] +
        [f"\tMetric: {i['var_1']}\n"] +
        [f"\tNormalised: {i['var_2']}\n"] +
        [f"\tAccuracy: {i['var_3']}\n"] +
        [f"\tDeviation: {i['var_4']}\n"]
        for i in _expected
    ]

    def run_simulation(out_file: str, trigger, file_content: list[list[str]]=_file_blocks, interval:float=_refresh_interval) -> None:
        for block in file_content:
            time.sleep(interval)
            with open(out_file, "a") as out_f:
                out_f.writelines(block)
        trigger.set()

    @dataclasses.dataclass
    class Counter:
        value: int = 0

    _counter = Counter()

    def callback_check(data, meta, comparison=_expected, counter=_counter) -> None:
        for key, value in data.items():
            assert value == comparison[counter.value][key]
        counter.value += 1

    @mp_parse.log_parser
    def parser_func(file_content: str, **_) -> tuple[dict[str, typing.Any], list[dict[str, typing.Any]]]:
        _regex_search_str = r"\s*Data Out\n\s*Result:\ (\d+\.\d+)\n\s*Metric:\ (\d+\.\d+)\n\s*Normalised:\ (\d+\.\d+)\n\s*Accuracy:\ (\d+\.\d+)\n\s*Deviation:\ (\d+\.\d+)"

        _parser = re.compile(_regex_search_str, re.MULTILINE)
        _out_data = []

        for match_group in _parser.finditer(file_content):
            _out_data += [
                {f"var_{i}": float(match_group.group(i+1)) for i in range(5)}
            ]
        return {}, _out_data

    with tempfile.NamedTemporaryFile(suffix=".log") as temp_f:
        _termination_trigger = multiprocessing.Event()
        _process = multiprocessing.Process(target=run_simulation, args=(temp_f.name,_termination_trigger))

        with multiparser.FileMonitor(
            per_thread_callback=callback_check,
            termination_trigger=_termination_trigger,
            interval=0.1*_refresh_interval,
            log_level=logging.DEBUG,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.tail(
                path_glob_exprs=[temp_f.name],
                parser_func=parser_func,
                skip_lines_w_pattern=[re.compile(_gen_ignore_pattern)]
            )
            _process.start()
            monitor.run()
            _process.join()


@pytest.mark.parsing
@pytest.mark.parametrize(
    "delimiter", (",", " "),
    ids=("comma", "whitespace")
)
@pytest.mark.parametrize(
    "explicit_headers", ("no_headers", "headers", "headers_search")
)
def test_parse_delimited_in_blocks(delimiter, explicit_headers) -> None:
    _refresh_interval: float = 0.1
    _xeger = xeger.Xeger(seed=XEGER_SEED)

    # Cases where user provides the headers, or they are read as first line in file
    if explicit_headers == "headers":
        _headers = [f"num_{i}" for i in range(5)]
        _header_search = None
        _expected = [{k: random.random() * 10 for k in _headers} for _ in range(40)]
        _file_blocks = []
    elif explicit_headers == "headers_search":
        _headers = None
        _header_search = re.compile(r"var_", re.IGNORECASE)
        _expected = [{f"var_{i}": random.random() * 10 for i in range(5)} for _ in range(40)]
        _file_blocks = [
            _xeger.xeger("\w+\s\w+") + "\n" for _ in range(2) 
        ]
    else:
        _headers = None
        _header_search = None
        _expected = [{f"var_{i}": random.random() * 10 for i in range(5)} for _ in range(40)]
        _file_blocks = [delimiter.join(f"var_{i}" for i in range(5)) + "\n"]

    _gen_ignore_pattern = r"<!--ignore-this-\w+-\d+-->"
    _file_blocks += [_xeger.xeger(_gen_ignore_pattern) + "\n"]

    if explicit_headers == "headers_search":
        _file_blocks += [delimiter.join(f"var_{i}" for i in range(5)) + "\n"]

    _file_blocks += [
        delimiter.join(map(str, row.values())) + "\n"
        for row in _expected
    ]

    @dataclasses.dataclass
    class Counter:
        value: int = 0

    _counter = Counter()

    def run_simulation(out_file: str, trigger, file_content: list[list[str]]=_file_blocks, interval:float=_refresh_interval) -> None:
        current_line = 0
        while current_line + (n_lines := random.randint(4, 6)) < len(file_content):
            time.sleep(interval)
            with open(out_file, "a") as out_f:
                out_f.writelines(file_content[current_line:current_line+n_lines])
            current_line += n_lines
        trigger.set()

    def callback_check(data, _, comparison=_expected, counter=_counter) -> None:
        for key, value in data.items():
            assert value == comparison[counter.value][key]
        counter.value += 1

    with tempfile.NamedTemporaryFile(suffix=".csv") as temp_f:
        _termination_trigger = multiprocessing.Event()
        _process = multiprocessing.Process(target=run_simulation, args=(temp_f.name,_termination_trigger))

        with multiparser.FileMonitor(
            per_thread_callback=callback_check,
            termination_trigger=_termination_trigger,
            interval=0.1*_refresh_interval,
            log_level=logging.DEBUG,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.tail(
                path_glob_exprs=[temp_f.name],
                parser_func=tail_record_delimited,
                parser_kwargs={"delimiter": delimiter, "headers": _headers, "header_pattern": _header_search},
                skip_lines_w_pattern=[re.compile(_gen_ignore_pattern)]
            )
            _process.start()
            monitor.run()
            _process.join()


@pytest.mark.parsing
def test_parse_h5() -> None:
    _data_file: str = os.path.join(DATA_LIBRARY, "example.h5")

    @file_parser
    def parser_func(input_file: str, **_) -> tuple[dict[str, typing.Any, dict[str, typing.Any]]]:
        return {}, pandas.read_hdf(file_name, key={"key": "my_group/my_dataset"}).to_dict()

    with multiparser.FileMonitor(
        per_thread_callback=lambda *_, **__: (),
        log_level=logging.DEBUG,
        terminate_all_on_fail=True
    ) as monitor:
        monitor.track(
            path_glob_exprs=_data_file,
            parser_func=parser_func,
            static=True
        )
        monitor.run()
        monitor.terminate()


@pytest.mark.monitor
def test_timeout_trigger() -> None:
    _timeout: int = 5
    _test_passed = multiprocessing.Value('i', 0)

    def timer_test(trigger, timeout, passed) -> None:
        _start_time = time.time()
        _test_timeout = 0
        while not trigger.is_set():
            _test_timeout += 0.1
            time.sleep(0.1)
            if _test_timeout >= timeout + 2:
                passed.value = 1000000
                return
        _end_time = time.time()
        passed.value = int(_end_time - _start_time)
    
    with multiparser.FileMonitor(
        per_thread_callback=lambda *_, **__: (),
        log_level=logging.DEBUG,
        timeout=_timeout,
        terminate_all_on_fail=True
    ) as monitor:
        monitor.run()
        _process = multiprocessing.Process(
            target=timer_test,
            args=(monitor._monitor_termination_trigger, _timeout, _test_passed)
        )

        _process.start()
        _process.join()

        if _test_passed.value == 1000000:
            raise AssertionError("Test failed due to infinite loop")
        assert _test_passed.value == _timeout


@pytest.mark.parsing
@pytest.mark.parametrize(
    "scenario", ("invalid_argument", "no_arbitrary_keyword_args", "undecorated")
)
@pytest.mark.parametrize(
    "parser_type", ("file", "log")
)
def test_check_invalid_parser_functions(scenario: str, parser_type: str) -> None:
    if scenario == "invalid_argument":
        parser_func = lambda file_line: ({}, {})
    elif parser_type == "log":
        if scenario == "no_arbitrary_keyword_args":
            parser_func = lambda file_content: ({}, {})
        else:
            parser_func = lambda file_content, **_: ({}, {})
    elif parser_type == "file":
        if scenario == "no_arbitrary_keyword_args":
            parser_func = lambda input_file: ({}, {})
        else:
            parser_func = lambda input_file, **_: ({}, {})

    if scenario != "undecorated":
        parser_func = file_parser(parser_func) if parser_type == "file" else log_parser(parser_func)

    with multiparser.FileMonitor(
        log_level=logging.DEBUG,
        timeout=2,
        terminate_all_on_fail=True
    ) as monitor:
        with pytest.raises(AssertionError) as exc:
            if parser_type == "file":
                monitor.track(
                    path_glob_exprs="*",
                    parser_func=parser_func,
                    static=True
                )
            else:
                monitor.tail(
                    path_glob_exprs="*",
                    parser_func=parser_func,
                )
            monitor.run()

    if scenario == "invalid_argument":
        _exception = f"Expected keyword argument '{'input_file' if parser_type == 'file' else 'file_content'}'"
    elif scenario == "undecorated":
        _exception = f"must be decorated using the multiparser.{parser_type}_parser decorator"
    else:
        _exception = "must allow arbitrary number of keyword arguments"

    assert _exception in str(exc.value)


@pytest.mark.parsing
def test_file_parser_with_args() -> None:
    @file_parser
    def parse_file(input_file: str, skip_lines: int, **_) -> tuple[dict, dict]:
        with open(input_file) as in_file:
            lines = in_file.readlines()
        if skip_lines:
            lines = lines[skip_lines:]
        return {}, {"lines": lines}


    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_csv(temp_d)
        _skip_lines = 2
        with open(_data_file) as in_f:
            n_lines = len(in_f.readlines())

        def callback_check(data, _, n_lines=n_lines) -> None:
            assert len(data["lines"]) == n_lines - _skip_lines

        with multiparser.FileMonitor(
            per_thread_callback=callback_check,
            log_level=logging.DEBUG,
            timeout=2,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.track(
                path_glob_exprs=_data_file,
                parser_func=parse_file,
                parser_kwargs={"skip_lines": _skip_lines},
                static=True
            )
            monitor.run()


@pytest.mark.parsing
def test_log_parser_with_args() -> None:
    @log_parser
    def parse_line(file_content: str, word_count: int, **_) -> tuple[dict, dict]:
        _words = file_content.split(" ")
        if word_count:
            if len(_words) < word_count:
                _words = word_count * [_words]
            _words = _words[:word_count]
        return {}, {"words": _words}


    with tempfile.TemporaryDirectory() as temp_d:
        _data_file = fake_csv(temp_d)
        _word_count = 2

        def callback_check(data, _, word_count=_word_count) -> None:
            assert len(data["words"]) == _word_count

        with multiparser.FileMonitor(
            per_thread_callback=callback_check,
            log_level=logging.DEBUG,
            timeout=2,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.tail(
                path_glob_exprs=_data_file,
                parser_func=parse_line,
                parser_kwargs={"word_count": _word_count},
            )
            monitor.run()
        

@pytest.mark.monitor
@pytest.mark.parametrize(
    "style", ("normal", "mixed", "list")
)
def test_custom_parser(style: str) -> None:
    METADATA = {"meta": 2, "demo": "test"}
    DATA = {"a": 2, "b": 3.2, "c": "test"}
    @mp_parse.file_parser
    def _parser_func(input_file: str, style=style, **_):
        if style == "normal":
            return METADATA, DATA
        elif style == "mixed":
            return METADATA, 10 * [DATA]
        else:
            return 10 * [(METADATA, DATA)]
        
    with tempfile.TemporaryDirectory() as temp_d:
        _timeout: int = 5
        def dummy_file(out_dir: str=temp_d, timeout: int=_timeout) -> None:
            with open(os.path.join(out_dir, "test.tst")) as out_f:
                out_f.write("testing")
            time.sleep(timeout)
        with multiparser.FileMonitor(
            per_thread_callback=lambda *_, **__: (),
            log_level=logging.DEBUG,
            timeout=_timeout,
            terminate_all_on_fail=True
        ) as monitor:
            monitor.run()
            monitor.track(
                path_glob_exprs=["*.tst"],
                tracked_values=None,
                parser_func=_parser_func
            )
            _process = multiprocessing.Process(
                target=dummy_file,
            )

            _process.start()
            _process.join()


@pytest.mark.monitor
@pytest.mark.parametrize(
    "parser", ("valid_parser", "not_decorated", "bad_return", "raises_exc")
)
def test_custom_log_parser(parser: str) -> None:
    def _undecorated_custom_log_parser(file_content: str, *_, **__):
        return {}, {"some_data": 2, "content": file_content}
    
    @mp_parse.log_parser
    def _good_custom_log_parser(file_content: str, *_, **__):
        return _undecorated_custom_log_parser(file_content)
    
    @mp_parse.log_parser
    def _bad_return_custom_log_parser(file_content: str, *_, **__):
        return file_content, "oops"
    
    @mp_parse.log_parser
    def _bad_raises_custom_log_parser(file_content: str, *_, **__):
        raise RuntimeError("Oops")
    
    if parser == "valid_parser":
        with multiparser.FileMonitor(
            lambda *_: None,
            log_level=logging.INFO,
            terminate_all_on_fail=True,
            timeout=2
        ) as monitor:
            monitor.tail(
                path_glob_exprs=["files*"],
                parser_func=_good_custom_log_parser
            )
    elif parser == "undecorated":
        with pytest.raises(AssertionError) as e:
            with multiparser.FileMonitor(
                lambda *_: None,
                log_level=logging.INFO,
                terminate_all_on_fail=True,
                timeout=2
            ) as monitor:
                monitor.tail(
                    path_glob_exprs=["files*"],
                    parser_func=_undecorated_custom_log_parser
                )
                assert "Parser function must be decorated" in str(e.value)
    elif parser == "bad_return":
        with pytest.raises(AssertionError) as e:
            with multiparser.FileMonitor(
            lambda *_: None,
                log_level=logging.INFO,
                terminate_all_on_fail=True,
                timeout=2
            ) as monitor:
                monitor.tail(
                path_glob_exprs=["files*"],
                parser_func=_bad_return_custom_log_parser
            )
            assert "Parser function must return two objects, " in str(e.value)
    else:
        with pytest.raises(AssertionError) as e:
            with multiparser.FileMonitor(
            lambda *_: None,
                log_level=logging.INFO,
                terminate_all_on_fail=True,
                timeout=2
            ) as monitor:
                monitor.tail(
                path_glob_exprs=["files*"],
                parser_func=_bad_raises_custom_log_parser
            )
            assert "Custom parser testing failed with exception" in str(e.value)
