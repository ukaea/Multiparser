"""
Multiparser
===========

Main multiparser module which provides access to the FileMonitor object
for monitoring outputs. Also sets up logging.
"""

__date__ = "2023-10-16"
__author__ = "Kristian Zarebski"
__maintainer__ = "Kristian Zarebski"
__email__ = "kristian.zarebski@ukaea.uk"
__copyright__ = "Copyright 2024, United Kingdom Atomic Energy Authority"

import loguru
import toml
import importlib.metadata
import os.path
import pathlib

from multiparser.monitor import FileMonitor as FileMonitor

try:
    __version__ = importlib.metadata.version("multiparser")
except importlib.metadata.PackageNotFoundError:
    _metadata = os.path.join(
        pathlib.Path(os.path.dirname(__file__)).parents[1], "pyproject.toml"
    )
    if os.path.exists(_metadata):
        __version__ = toml.load(_metadata)["project"]["version"]
    else:
        __version__ = ""

__all__ = ["FileMonitor"]

loguru.logger.remove()
