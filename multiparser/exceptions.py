"""
Custom Exceptions
=================

Exceptions for handling failures within individual file monitoring threads
"""

import traceback


class FileMonitorThreadException(Exception):
    """Execption captured and re-raised by a single file monitoring thread"""

    def __init__(self, file_thread_exceptions: dict[str, Exception | None]) -> None:
        """Initialise the file monitor exception with those gathered from threads"""
        self.exceptions = file_thread_exceptions


class SessionFailure(Exception):
    """Top level exception for throwing all collected exceptions from child threads"""

    def __init__(self, exceptions_dict: dict[str, BaseException]) -> None:
        """Initialise the top-level exception with collected exceptions

        Assembles all exceptions into info string
        """
        _info_str: str = ""
        for name, exception in exceptions_dict.items():
            _info_str += f"{name}:\n\t\t"
            _info_str += "\n\t\t".join(traceback.format_exception(exception))
        super().__init__(
            f"Multiparser session encountered the following exceptions:\n\t{_info_str}"
        )
