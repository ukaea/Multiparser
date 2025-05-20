# Development

## Using UV

The _Multiparser_ repository makes use of the [UV](https://docs.astral.sh/uv/) which is a pip-installable dependency management and virtual environment tool for assisting development, and recommended when contributing to the project. The included `uv.lock` file provides a shareable virtual environment definition. UV is able to resolve dependency versions to ensure cross-compatibility.

## Pre-commit

The repository includes a pre-commit configuration file which can be used to setup git hooks executed during committing. To install the hooks firstly ensure [pre-commit](https://pre-commit.com/) is installed then run:

```sh
pre-commit install
```

within the repository. You can manually run all hooks by executing:

```sh
pre-commit run --all
```

## Documentation

_Multiparser_ follows the Numpy docstring convention for outlining function and class parameters and return types.

Included within the git hooks is the docstring coverage check tool [_interrogate_](https://pypi.org/project/interrogate/) which checks whether all functions within the `multiparser` module have been documented. The tool can be run in isolation using UV:

```sh
uv run interrogate
```
