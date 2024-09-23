
# 2023-09-23 [v1.0.3](https://github.com/ukaea/Multiparser/releases/tag/v1.0.3)

* Removed unneeded parameter printout in `monitor.py`.

# 2023-08-21 [v1.0.2](https://github.com/ukaea/Multiparser/releases/tag/v1.0.2)

* Added support for parser keyword arguments in file parsers.
* Added additional custom parser checking.
* Added support for both positional and keyword argument propagation allowing parsers to be created from class methods.

# 2023-03-26 [v1.0.1](https://github.com/ukaea/Multiparser/releases/tag/v1.0.1)

* Fixed broken tail parsers due to incorrect handling of outputs.
* Fixed bug whereby only one file in a group (e.g. `*.txt`) is parsed when `terminate_all_on_fail` is set.

# 2024-03-22 [v1.0.0](https://github.com/ukaea/Multiparser/releases/tag/v1.0.0)

* Added ability for FileMonitor to itself set termination triggers to stop external processes if required.
* Added exception handling across all threads whereby any errors occurring in a thread are raised either after the monitor is terminated or causing all threads to be aborted.
* Added functionality for users to create their own custom parsers in both categories.
* Included default parsers for common file types such as JSON, CSV, YAML etc.
* Implemented termination trigger and timeout to allow the user to either abort monitoring via an external process, or set an expiry period.
* Created FileMonitor for observing changes to files specified by the user separating these into two categories "tracked" for files read in full, and "tailed" for those where only added lines are parsed.
