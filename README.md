<p align="center">
<img src="https://raw.githubusercontent.com/ukaea/Multiparser/main/docs/media/logo.png", width="200">
</p>

# Multiparser
[![PyPI Latest Release](https://img.shields.io/pypi/v/ukaea-multiparser.svg)](https://pypi.org/project/ukaea-multiparser/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ukaea-multiparser)
 [![multiparser](https://github.com/ukaea/multiparser/actions/workflows/test_run_multiparser.yaml/badge.svg?branch=main)](https://github.com/ukaea/multiparser/actions/workflows/test_run_multiparser.yaml)
 [![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

_Multiparser_ is module for performing functionality across a set of output files. Given a set of files, and optionally a list of output parameter names or regex filters the module keeps track of changes by monitoring the "last modified" timestamp of each file and executing the assigned callback.

For example, in the case where a set of model outputs were written to a set of files the user is able to specify which files are of importance, the variables to be noted within these files, and a function to execute whenever a change is made to one of these files.

## Installation

The module is available in PyPi:

```sh
pip install ukaea-multiparser
```

To install optional extras `arrow` and `fortran` list them during the install, e.g.:

```sh
pip install ukaea-multiparser[fortran,arrow]
```

## Example

```python
with FileMonitor(
    per_thread_callback=callback_function,
    lock_callback=True,
    interval=10.0,
    flatten_data=True
) as monitor:
    monitor.track(
        path_glob_exprs=["file_of_interest.toml", "out_dir/*.other"],
        tracked_values=[
            "list", "of", "interesting", "values",
            re.compile(r"^list"),
            re.compile(r"of\s"),
            re.compile(r"regular"),
            re.compile(r"Expressions")
        ],
        static=True
    )
    monitor.run()
    ...
    monitor.terminate()
```

## Documentation

For information on use and functionality please see the [documentation](https://ukaea.github.io/Multiparser/).

## Licensing

_Multiparser_ is provided under the MIT license allowing reuse within both open source and proprietary software.

## Contributing

For contributions and development towards improving _Multiparser_ please see the included [CONTRIBUTING.md](https://github.com/ukaea/Multiparser/blob/main/CONTRIBUTING.md) file.

---

Copyright (c) 2024 UK Atomic Energy Authority
