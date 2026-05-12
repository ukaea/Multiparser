# `FileMonitor.tail`

The `FileMonitor` method `tail` is used to monitor _appended_ changes to files, that is content which has been added to the file incrementally, for example log files containing the `stdout` of a given process.

```python
monitor.tail(
    path_glob_exprs="*.log",
    tracked_values=[re.compile(r'^(\w+)=(\d+))', re.compile(r'\w+=([\d\.]+)')],
    labels=[None, "fraction"],
    callback=lambda data, _: logging.getLogger("Simulation").info(data),
    parser_func=None,
    parser_kwargs=None
)
```

## Arguments

### `path_glob_exprs`
`#!python list[str] | str`

Either a single globular expression string or a list of such strings defining files to be monitored by this tail, can be an explicit string if only one file is required.

### `tracked_values` <a id="tracked-values"></a>
`#!python list[str | Pattern] | str | Pattern | None`

Default: `None`

Either a single string or regular expression, or a list of a combination of either defining values to be recorded. In general a regular expression applies here as it provides a pattern for recording, a string may be used if waiting for the appearance of a statement explicitly. Regular expressions must be `re.compile` objects.

Regular expressions can have either one capture group representing the value to capture, or two representing the key and the value. Note when only one regex group or a string is specified a label must also be present (see [`labels`](#labels)).

```python
tracked_values = [
    "END OF LINE",  # Wait for exact string (requires label)
    re.compile(r'(\w+)=(\d+)'), # Specify label/key and value to capture
    re.compile(r'\w+=(\d+)') # Specify only value to capture (requires label)
]
```

### `skip_lines_w_pattern`
`#!python list[Pattern | str] | None`

Default: `None`

A list of patterns or strings defining lines to exclude when parsing a file. The patterns are `re.compile` objects as above:

```python
skip_lines_w_pattern = ["# Header", re.compile(r'^# Begin (\w+)')]
```

### `labels`
`#!python list[str] | None`

Default: `None`

Labels define the key associated with each captured value, in the case where either a string or a single regex capture group is used (see [`tracked_values`](#tracked-values)) this is mandatory, else in other cases it will overwrite the capture group:

```python
tracked_values = [
    "END OF LINE",  # Wait for exact string (requires label)
    re.compile(r'(\w+)=(\d+)'), # Specify label/key and value to capture
    re.compile(r'\w+=(\d+)') # Specify only value to capture (requires label)
]

# Scenario 1: Assign labels to first and last tracked_values definition
# labels for first and last entries are mandatory
labels = ["eof", None, "key"]

# Scenario 2: As above but overwrite key captured by regex in second entry
labels = ["eof", "new_key", "key"]
```

### `callback`
`#!python Callable[[dict[str, Any], dict[str, Any]], None] | None`

Default: `None`

Optional callback exclusively for this file set, this overwrites the global callback (if specified) within the `FileMonitor` definition (see [here](./file_monitor.md#per-thread-callback)).


### `parser_func`
`#!python Callable[[str, *_], tuple[dict[str, Any], dict[str, Any]]] | None`

Default: `None`

Specific a custom parser for this file set, this must be a log parsing function wrapped in the `multiparser.parsing.tail.log_parser` decorator, for more information see [here](./custom_parsers.md#log-parsers).

### `parser_kwargs`
`#!python dict[str, Any] | None`

Default: `None`

Keyword arguments to pass to the function defined above, useful if you want to specify near-identical parsing of multiple file sets with slight customisation.

## Returns

`#!python None`
