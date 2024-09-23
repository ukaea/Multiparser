"""
Multiparser File Monitor
========================

Contains a class for defining how to track the changes within output files
created by a process. These files can be defined by name or using globular
expressions, with content of significance then being defined using regular
expressions. The files are split into log files where the last line is read
on modification, and full files where the whole file is read and parsed as
a whole.

"""

__date__ = "2023-10-16"
__author__ = "Kristian Zarebski"
__maintainer__ = "Kristian Zarebski"
__email__ = "kristian.zarebski@ukaea.uk"
__copyright__ = "Copyright 2024, United Kingdom Atomic Energy Authority"

import contextlib
import glob
import logging
import multiprocessing
import re
import string
import sys
import threading
import inspect
import time
import typing
from multiprocessing.synchronize import Event

import loguru

import multiparser.exceptions as mp_exc
import multiparser.thread as mp_thread
from multiparser.typing import FullFileTrackable, LogFileTrackable, TrackedValues

__all__ = ["FileMonitor"]


def _default_callback(
    _: typing.Dict[str, typing.Any], meta: typing.Dict[str, typing.Any]
) -> None:
    """Default per file callback if none set globally or per file"""
    loguru.logger.warning(
        f"Changes detected but no callback set for {meta['file_name']}."
    )


def _check_log_globex(trackables: list[LogFileTrackable]) -> None:
    """Check globular expressions before passing them to thread"""
    for expression in trackables:
        if not isinstance(_glob_ex := expression["glob_expr"], str):
            raise AssertionError("Globular expression must be of type AnyStr")
        glob.glob(_glob_ex)


class FileMonitor:
    """The FileMonitor class is used to monitor a directory for file changes

    The monitor can be used to watch files matching globular expressions defined by the
    user. When a change is detected a user specified callback is triggered on the newly
    parsed data. There are two types of monitoring:

    * Full File: this loads the file as a whole each time a change is registered.
    * Log File: only the latest content is parsed.

    The main thread talks to the file monitor via a dictionary which holds information
    from the latest round of file parsing. When the main thread has processed the gathered
    information it will clear the entries preventing over-caching.
    """

    def __init__(
        self,
        per_thread_callback: typing.Callable | None = None,
        exception_callback: typing.Callable | None = None,
        notification_callback: typing.Callable | None = None,
        termination_trigger: Event | None = None,
        subprocess_triggers: typing.List[Event] | None = None,
        timeout: int | None = None,
        lock_callbacks: bool = True,
        interval: float = 0.1,
        log_level: int | str = logging.INFO,
        flatten_data: bool = False,
        plain_logging: bool = False,
        terminate_all_on_fail: bool = False,
        file_limit: int | None = 50,
    ) -> None:
        """Create an instance of the file monitor for tracking file modifications.

        Parameters
        ----------
        threads_recorder : typing.Dict
            Dictionary for caching values read from the file parsing threads
        per_thread_callback : typing.Callable, optional
            function to be executed whenever a monitored file is modified
            this will apply globally to all files unless overwritten
        exception_callback : typing.Callable | None, optional
            function to be executed when an exception is thrown
        notification_callback : typing.Callable | None, optional
            function to be called when a new file is found, default is
            a print statement
        subprocess_triggers : typing.List[Event], optional
            if provided, events which will be set if monitor terminates
        timeout : int, optional
            time after which to terminate, default is None
        lock_callback : bool, optional
            whether to only allow one thread to execute the callbacks
            at a time. Default is True.
        interval : float, optional
            the refresh rate of the file monitors, by default 0.1 seconds
        log_level : int | str, optional
            log level for this object
        flatten_data : bool, optional
            whether to convert data to a single level dictionary of key-value pairs
        plain_logging : bool, optional
            turn off color/symbols in log outputs, default False
        terminate_all_on_failure : bool, optional
            abort all file monitors if exception thrown, default False
        file_limit : int, optional
            maximum number of files to be monitored, limits number of threads
            each of the two monitor types can start, if None no limit. Default 100.
        """
        self._interval: float = interval
        self._timeout: int | None = timeout
        self._per_thread_callback = per_thread_callback or _default_callback
        self._notification_callback = notification_callback
        self._shutdown_on_thread_failure: bool = terminate_all_on_fail
        self._exceptions: typing.Dict[str, Exception | None] = {}
        self._exception_callback = self._generate_exception_callback(exception_callback)
        self._file_threads_mutex: "threading.Lock | None" = (
            threading.Lock() if lock_callbacks else None
        )
        self._subprocess_triggers: typing.List[Event] | None = subprocess_triggers
        self._monitor_termination_trigger = (
            termination_trigger or multiprocessing.Event()
        )
        self._known_files: typing.List[str] = []
        self._file_trackables: typing.List[FullFileTrackable] = []
        self._log_trackables: typing.List[LogFileTrackable] = []
        self._excluded_patterns: typing.List[str] = []
        self._file_monitor_thread: threading.Thread | None = None
        self._log_monitor_thread: threading.Thread | None = None
        self._timer_process: multiprocessing.Process | None = None
        self._flatten_data: bool = flatten_data
        self._thread_limit: int | None = file_limit

        # Used for testing only
        self._file_thread_exception_test_case: bool = False
        self._log_thread_exception_test_case: bool = False

        _plain_log: str = "{elapsed} | {level: <8} | multiparser | {message}"
        _color_log: str = "{level.icon} | <green>{elapsed}</green>  | <level>{level: <8}</level> | <c>multiparser</c> | {message}"

        self._log_id = loguru.logger.add(
            sys.stderr,
            format=_plain_log if plain_logging else _color_log,
            colorize=not plain_logging,
            level=log_level,
        )

    def _generate_exception_callback(
        self, user_callback: typing.Callable | None
    ) -> typing.Callable:
        def _exception_callback(
            exception: Exception,
            _exceptions: dict[str, Exception | None] = self._exceptions,
            user_defined=user_callback,
            abort_on_fail=self._shutdown_on_thread_failure,
            abort_func=self.terminate,
        ) -> None:
            if user_defined:
                user_defined(f"{type(exception).__name__}: '{exception.args[0]}'")

            if abort_on_fail:
                loguru.logger.error("Detected file monitor thread failure, aborting...")
                abort_func()

            if isinstance(exception, mp_exc.FileMonitorThreadException):
                _exceptions |= exception.exceptions
            else:
                _exceptions["__main__"] = exception

        return _exception_callback

    def _create_monitor_threads(self) -> None:
        """Create threads for the log file and full file monitors"""

        def _full_file_monitor_func(
            ff_trackables: typing.List[FullFileTrackable],
            exc_glob_exprs: typing.List[str],
            file_list: typing.List[str],
            termination_trigger: threading.Event,
            interval: float,
            flatten_data: bool,
        ) -> None:
            """Creates and runs thread launcher for full file monitoring"""
            _full_file_threads = mp_thread.FullFileThreadLauncher(
                trackables=ff_trackables,
                exclude_files_globex=exc_glob_exprs,
                refresh_interval=interval,
                file_limit=self._thread_limit,
                file_list=file_list,
                file_thread_lock=self._file_threads_mutex,
                abort_on_fail=self._shutdown_on_thread_failure,
                file_thread_termination_trigger=termination_trigger,
                exception_callback=self._exception_callback,
                notification_callback=self._notification_callback,
                flatten_data=flatten_data,
                test_exception_capture=self._file_thread_exception_test_case,
            )
            _full_file_threads.run()

        def _log_file_monitor_func(
            lf_trackables: typing.List[LogFileTrackable],
            exc_glob_exprs: typing.List[str],
            file_list: typing.List[str],
            termination_trigger: threading.Event,
            interval: float,
            flatten_data: bool,
        ) -> None:
            """Creates and runs thread launcher for log file monitoring"""
            _log_file_threads = mp_thread.LogFileThreadLauncher(
                trackables=lf_trackables,
                exclude_files_globex=exc_glob_exprs,
                refresh_interval=interval,
                file_limit=self._thread_limit,
                file_list=file_list,
                file_thread_lock=self._file_threads_mutex,
                file_thread_termination_trigger=termination_trigger,
                exception_callback=self._exception_callback,
                abort_on_fail=self._shutdown_on_thread_failure,
                notification_callback=self._notification_callback,
                flatten_data=flatten_data,
                test_exception_capture=self._log_thread_exception_test_case,
            )
            _log_file_threads.run()

        self._file_monitor_thread = threading.Thread(
            target=_full_file_monitor_func,
            args=(
                self._file_trackables,
                self._excluded_patterns,
                self._known_files,
                self._monitor_termination_trigger,
                self._interval,
                self._flatten_data,
            ),
        )

        self._log_monitor_thread = threading.Thread(
            target=_log_file_monitor_func,
            args=(
                self._log_trackables,
                self._excluded_patterns,
                self._known_files,
                self._monitor_termination_trigger,
                self._interval,
                self._flatten_data,
            ),
        )

    def _check_custom_log_parser(
        self, parser: typing.Callable, **parser_kwargs
    ) -> None:
        """Verifies the parser works correctly before launching threads"""
        if hasattr(parser, "__skip_validation"):
            return

        _func_signature = inspect.signature(parser)
        _parameters = list(_func_signature.parameters.values())

        if "file_content" not in (p.name for p in _parameters):
            raise AssertionError(
                f"Expected keyword argument 'file_content' in definition of parser function '{parser.__name__}'"
            )

        # The function must have **_ or **kwargs in the definition, this allows passing of internal
        # parameters prefixed with '__'
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in _parameters):
            raise AssertionError(
                f"Function '{parser.__name__}' must allow arbitrary number of keyword arguments, "
                "i.e. use '**_'"
            )

        _test_str = string.ascii_lowercase
        _test_str += string.ascii_uppercase
        _test_str += string.ascii_letters
        _test_str *= 100
        try:
            # Parsers are expected to have the keyword argument 'file_content'
            _out = parser(
                file_content=_test_str, __input_file=__file__, __read_bytes=None, **parser_kwargs
            )

            # If the custom parser returns a list of entries, not just one
            if isinstance(_out, list):
                _out = _out[0]

        except Exception as e:
            raise AssertionError(f"Custom parser testing failed for '{parser.__name__}' with exception:\n{e}")

        if (
            len(_out) != 2
            or not isinstance(_out[0], dict)
            or not isinstance(_out[1], (list, dict))
        ):
            raise AssertionError(
                f"Parser function '{parser.__name__}' must return two objects, a metadata dictionary and parsed values"
                " in the form of a dictionary or list of dictionaries"
            )

        # Either the parser itself is decorated, or a function it calls to create the parsed data
        # is decorated, either should add timestamp information
        if not parser.__name__.endswith("__mp_parser") and "timestamp" not in _out[0]:
            raise AssertionError(
                f"Parser function '{parser.__name__}' must be decorated using the "
                "multiparser.log_parser decorator"
            )

    def exclude(self, path_glob_exprs: typing.List[str] | str) -> None:
        """Exclude a set of files from monitoring.

        Parameters
        ----------
        path_glob_exprs : typing.List[str] | str
            a list or string defining globular expressions for files
            to exclude from tracking
        """
        if isinstance(path_glob_exprs, str):
            self._excluded_patterns.append(path_glob_exprs)
        else:
            self._excluded_patterns += path_glob_exprs

        # Check globular expressions before passing them to thread
        for expression in self._excluded_patterns:
            glob.glob(expression)

    def track(
        self,
        *,
        path_glob_exprs: typing.List[str] | str,
        tracked_values: TrackedValues | None = None,
        callback: typing.Callable | None = None,
        parser_func: typing.Callable | None = None,
        parser_kwargs: typing.Dict | None = None,
        static: bool = False,
        file_type: str | None = None,
    ) -> None:
        """Track a set of files.

        Tracking a file means reading the whole contents at a time,
        this should be reserved for file types whereby reading on a
        per line basis is unconventional (e.g. JSON etc), for such
        file types the file must be loaded in as a whole.

        Parameters
        ----------
        path_glob_exprs : typing.List[str] | str
            set of or single globular expression(s) defining files
            to monitor
        tracked_values : typing.List[str] | None, optional
            a list of regular expressions defining variables to track
            within the file, by default None
        callback : typing.Callable | None, optional
            override the global per file callback for this instance
        parser_func : typing.Callable | None, optional
            provide a custom parsing function
        parser_kwargs : typing.Dict | None, optional
            arguments to include when running the specified custom parser
        static : bool, optional
            (if known) whether the given file(s) are written only once
            and so looped monitoring is not required, by default False
        file_type : str, optional
            if using "lazy" parsing override the suffix based file type
            recognition with a recognised parser e.g. 'yaml'
        """

        if parser_func:
            _parameters = list(inspect.signature(parser_func).parameters.values())
            if "input_file" not in (p.name for p in _parameters):
                raise AssertionError(
                    f"Expected keyword argument 'input_file' in definition of parser function '{parser_func.__name__}'"
                )
            # Either the parser itself is decorated, or a function it calls to create the parsed data
            # is decorated, either should add timestamp information
            if not parser_func.__name__.endswith("__mp_parser"):
                raise AssertionError(
                    f"Parser function '{parser_func.__name__}' must be decorated using the "
                    "multiparser.file_parser decorator"
                )

            # The function must have **_ or **kwargs in the definition, this allows passing of internal
            # parameters prefixed with '__'
            if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in _parameters):
                raise AssertionError(
                    f"Function '{parser_func.__name__}' must allow arbitrary number of keyword arguments, "
                    "i.e. use '**_'"
                )

        if isinstance(path_glob_exprs, str):
            _parsing_dict: typing.Dict[str, typing.Any] = {
                "glob_expr": path_glob_exprs,
                "tracked_values": tracked_values,
                "static": static,
                "parser_func": parser_func,
                "parser_kwargs": parser_kwargs,
                "file_type": file_type,
                "callback": callback or self._per_thread_callback,
            }
            self._file_trackables.append(_parsing_dict)
        else:
            self._file_trackables += [
                {
                    "glob_expr": g,
                    "tracked_values": tracked_values,
                    "static": static,
                    "parser_func": parser_func,
                    "parser_kwargs": parser_kwargs,
                    "file_type": file_type,
                    "callback": callback or self._per_thread_callback,
                }
                for g in path_glob_exprs
            ]

        # Check globular expressions before passing them to thread
        for expression in self._file_trackables:
            if not isinstance(_glob_ex := expression["glob_expr"], str):
                raise AssertionError("Globular expression must be of type AnyStr")
            glob.glob(_glob_ex)


    def tail(
        self,
        *,
        path_glob_exprs: typing.List[str] | str,
        tracked_values: TrackedValues | None = None,
        skip_lines_w_pattern: typing.List[re.Pattern | str] | None = None,
        labels: str | typing.List[str | None] | None = None,
        callback: typing.Callable | None = None,
        parser_func: typing.Callable | None = None,
        parser_kwargs: typing.Dict | None = None,
    ) -> None:
        """Tail a set of files.

        Tailing a file means reading the last line of that file,
        the file(s) in question should be read line by line, e.g.
        for a log file.

        Capture groups for the regular expressions defining the values
        to monitor can have two forms:

        * A single regular expression group, e.g. re.compile(r'\\d+')
          or re.compile(r'(\\d+)') with a name present in 'labels',
          e.g. "my_var".

          ```python
          tail(
            tracked_values=[re.compile(r'(\\d+),'), re.compile(r'\\d\\.\\d+')],
            labels=['my_var', 'other']
          )
          ```

        * A double regular expression group, e.g. re.compile(r'(\\w+\\_var)=(\\d+)')
          where the first group is the label, and the second the value.

          ```python
          tail(tracked_values=[re.compile(r'(\\w+\\_var)=(\\d+)']))
          tail(
            tracked_values=[
                re.compile(r'(\\w+\\_var)=(\\d+)'),
                re.compile(r'(\\w+\\_i=(\\d+)')
            ]
          )
          ```

          This can be overwritten by providing a value for that group.

          ```python
          tail(tracked_values=[re.compile(r'(\\w+\\_var)=(\\d+)']))
          tail(
            tracked_values=[
                re.compile(r'(\\w+\\_var)=(\\d+)'),
                re.compile(r'(\\w+\\_i=(\\d+)')
            ],
            labels=['my_var', None]
          )
          ```

        Parameters
        ----------
        path_glob_exprs : typing.List[str] | str
            set of or single globular expression(s) defining files
            to monitor
        tracked_values : typing.List[Pattern | str], optional
            a set of regular expressions or strings defining variables to track.
            Where one capture group is defined the user must provide
            an associative label. Where two are defined, the first capture
            group is taken to be the label, the second the value.
        skip_lines_w_pattern : typing.List[Pattern | str], optional
            specify patterns defining lines which should be skipped
        labels : typing.List[str], optional
            define the label to assign to each value, if an element in the
            list is None, then a capture group is used. If labels itself is
            None, it is assumed all matches have a label capture group.
        callback : typing.Callable | None, optional
            override the global per file callback for this instance
        parser_func : typing.Callable | None, optional
            provide a custom parsing function
        parser_kwargs : typing.Dict | None, optional
            arguments to include when running the specified custom parser
        """
        if parser_func:
            self._check_custom_log_parser(parser_func, **(parser_kwargs or {}))

        if parser_func and tracked_values:
            raise AssertionError(
                "Cannot specify both tracked values and custom parser for monitor "
                "method 'tail'"
            )

        if parser_func and labels:
            raise AssertionError(
                "Cannot specify both labels and custom parser for monitor "
                "method 'tail'"
            )

        _tracked_values: typing.List[str | re.Pattern]
        _labels: typing.List[str | None]

        if tracked_values is None:
            _tracked_values = []
        elif not isinstance(tracked_values, (list, set, tuple)):
            _tracked_values = [tracked_values]
        else:
            _tracked_values = tracked_values

        if labels is None:
            _labels = []
        elif not isinstance(labels, (list, set, tuple)):
            _labels = [labels]
        else:
            _labels = labels

        if _labels and len(_labels) != len(_tracked_values):
            raise AssertionError(
                "Number of labels must match number of regular expressions in 'tail'."
            )

        if not _tracked_values or parser_func:
            _reg_lab_expr_pairing: (
                typing.List[typing.Tuple[str | None, re.Pattern[str] | str]] | None
            ) = None
        else:
            _labels = _labels or [None] * len(_tracked_values)
            _reg_lab_expr_pairing = [
                (label, reg_ex) for label, reg_ex in zip(_labels, _tracked_values)
            ]

        if skip_lines_w_pattern:
            parser_kwargs = parser_kwargs or {}
            parser_kwargs["ignore_lines"] = skip_lines_w_pattern

        if isinstance(path_glob_exprs, (str, re.Pattern)):
            _parsing_dict: typing.Dict[str, typing.Any] = {
                "glob_expr": path_glob_exprs,
                "tracked_values": _reg_lab_expr_pairing,
                "static": False,
                "parser_func": parser_func,
                "parser_kwargs": parser_kwargs,
                "callback": callback or self._per_thread_callback,
            }
            self._log_trackables.append(_parsing_dict)
        else:
            self._log_trackables += [
                {
                    "glob_expr": g,
                    "tracked_values": _reg_lab_expr_pairing,
                    "static": False,
                    "parser_func": parser_func,
                    "parser_kwargs": parser_kwargs,
                    "callback": callback or self._per_thread_callback,
                }
                for g in path_glob_exprs
            ]

        _check_log_globex(self._log_trackables)

    @classmethod
    def _spin_timer(cls, duration: int, trigger: Event) -> None:
        """When a timeout has been specified ensure trigger is set within period"""
        loguru.logger.debug(f"Using timeout of {duration}s")

        time.sleep(duration)

        if not trigger.is_set():
            loguru.logger.info(f"File monitor timeout called after {duration}s")
            trigger.set()

    def _launch_timer(self) -> None:
        """Run timeout timer if user has specified a timeout in seconds"""
        self._timer_process = multiprocessing.Process(
            target=self._spin_timer,
            args=(self._timeout, self._monitor_termination_trigger),
        )
        self._timer_process.start()

    def terminate(self) -> None:
        """Terminate all monitors."""
        self._monitor_termination_trigger.set()
        self._close_processes()

    def _close_processes(self) -> None:
        # If for some reason the user calls 'terminate' before run and is not
        # using file monitor as a context manager
        if not self._file_monitor_thread or not self._log_monitor_thread:
            raise AssertionError("FileMonitor must be used as a context manager.")

        with contextlib.suppress(RuntimeError):
            self._file_monitor_thread.join()

        with contextlib.suppress(RuntimeError):
            self._log_monitor_thread.join()

        # set any triggers the user has attached to this monitor
        if self._subprocess_triggers:
            for trigger in self._subprocess_triggers:
                trigger.set()

        if not self._known_files:
            loguru.logger.warning("No files were processed during this session.")

    def run(self) -> None:
        """Launch all monitors"""
        if not self._file_monitor_thread or not self._log_monitor_thread:
            raise AssertionError("FileMonitor must be used as a context manager.")
        if self._timeout:
            self._launch_timer()
        self._file_monitor_thread.start()
        self._log_monitor_thread.start()

    def __enter__(self) -> "FileMonitor":
        """Setup all threads"""
        self._create_monitor_threads()
        return self

    def __exit__(self, *_, **__) -> None:
        """Set termination trigger"""

        if self._timer_process and self._timer_process.is_alive():
            self._timer_process.join()

        if self._file_monitor_thread and self._file_monitor_thread.is_alive():
            self._file_monitor_thread.join()

        if self._log_monitor_thread and self._log_monitor_thread.is_alive():
            self._log_monitor_thread.join()

        if _mon_thread_exc := self._exceptions.get("__main__"):
            raise _mon_thread_exc

        _exceptions: dict[str, BaseException] = {
            k: v for k, v in self._exceptions.items() if v
        }

        if _exceptions:
            raise mp_exc.SessionFailure(_exceptions)

        loguru.logger.remove(self._log_id)
