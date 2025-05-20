# Custom Parsers

In the situation where the output files from a process are not processable by any of the built-in parsers, a custom parser can be created to extract the information of interest.

## File Parsers

File parsers are used for tracking, they take the path of an identified candidate as an argument, parse the data from that file and return a key-value mapping of the data of interest. To create a custom parser you will need to use the `multiparser.parsing.file.file_parser` decorator. The function should take an argument `input_file` which is the file path, and allow an arbitrary number of additional arguments (`**_`) to be compatible with the decorator. It should return either:

  - Two dictionaries containing relevant metadata (usually left blank), and the parsed information: `{...}, {...}`.
  - A single dictionary representing the metadata, and a list of dictionaries (for cases where multiple lines are read in a single parse and these should be kept separate): `{...}, [{...}, ...]`

```python
from typing import Any
import multiparser.parsing.file as mp_file_parse

@mp_file_parse.file_parser
def parse_user_file_type(input_file: str, **_) -> tuple[dict[str, Any], dict[str, Any]]:
    with open(file_path) as in_f:
        file_lines = in_f.readlines()

    data = {}

    for line in file_lines:
        key, value = line.split(":", 1)
        data[key.strip().lower().replace(" ", "_")] = value.strip()

    return {}, data
```

To use the parser within a `FileMonitor` session:

```python
with multiparser.FileMonitor(timeout=10) as monitor:
    monitor.track(path_glob_exprs="custom_file.log", parser_func=parser_user_file_type)
    monitor.run()
```

In the case where you would like your parser function to accept additional keyword arguments you can add these
to the definition and pass them to tracking using the `parser_kwargs` argument.

!!! warning "Empty Data"
    The `per_thread_callback` of `FileMonitor` only executes when new data is parsed from a modified file,
not when the file is marked as modified. Therefore a custom parser which either does not return data, or
    returns explicitly an empty dictionary will never trigger the `per_thread_callback` method.

## Log Parsers

In the case where the custom parser will be used in file "tailing", that is read only the latest information appended to the file, the `multiparser.parsing.tail.log_parser` decorator is used when defining the function. The function should take an argument `file_content` which is a string containing the latest read content, and allow an arbitrary number of additional arguments (`**_`) to be compatible with the decorator. It should return either:

   - Two dictionaries containing relevant metadata (usually left blank), and the parsed information: `{...}, {...}`.
   - A single dictionary representing the metadata, and a list of dictionaries (for cases where multiple lines are read in a single parse and these should be kept separate: `{...}, [{...}, ...]`.

```python
from typing import Any
import multiparser.parsing.tail as mp_tail_parse

@mp_tail_parse.log_parser
def parse_user_file_type(file_content: str, **_) -> tuple[dict[str, Any], dict[str, Any]]:
    file_lines = file_content.split("\n")

    data = {}

    for line in file_lines:
        key, value = line.split(":", 1)
        data[key.strip().lower().replace(" ", "_")] = value.strip()

    return {}, data
```

To use the parser within a `FileMonitor` session:

```python
with multiparser.FileMonitor(timeout=10) as monitor:
    monitor.tail(path_glob_exprs="custom_file.log", parser_func=parser_user_file_type)
    monitor.run()
```

In the case where you would like your parser function to accept additional keyword arguments you can add these
to the definition and pass them to tracking using the `parser_kwargs` argument.

## Class methods as parsers

When custom parsers are decorated any positional and keyword arguments are propagated through, i.e.:

```python
@log_parser
def my_parser(a_position_arg, file_content, a_keyword_argument):
  ...
```

will be called as:

```python
my_parser(*args, file_content=file_content, **kwargs)
```

This allows class methods to also work as custom parsers because `self` is handled correctly:

```python
class MyClass:
  def __init__(self):
    ...

  @log_parser
  def my_parser(self, file_content):
    ...
```

!!! warning "Empty Data"
    The `per_thread_callback` of `FileMonitor` only executes when new data is parsed from a modified file,
not when the file is marked as modified. Therefore a custom parser which either does not return data, or
    returns explicitly an empty dictionary will never trigger the `per_thread_callback` method.
