import tempfile
import os.path
import logging
import multiparser.parsing.file as mp_file_parser
import multiparser.parsing.tail as mp_log_parser
import multiparser
import json


class ParserClass:
    
    @mp_file_parser.file_parser
    def _custom_file_parser(
        self,
        input_file: str,
        **__):
        return {}, json.load(open(input_file))

    @mp_log_parser.log_parser
    def _custom_log_parser(
        self,
        file_content: str,
        **__):
        return {}, {"input": file_content}

    def _my_callback(
        self,
        data,
        metadata
    ):
        print(data)

    def launch(self):
        # Start an instance of the file monitor, to keep track of log and results files
        with multiparser.FileMonitor(log_level=logging.DEBUG, terminate_all_on_fail=False, timeout=1
        ) as self.file_monitor:
            # Monitor each file created by a Vector PostProcessor, and upload results to Simvue if file matches an expected form.
            self.file_monitor.track(
                path_glob_exprs =  "test.json",
                parser_func = self._custom_file_parser,
                callback = self._my_callback,
            )
            self.file_monitor.tail(
                path_glob_exprs =  "test.json",
                parser_func = self._custom_log_parser,
                callback = self._my_callback,
            )
            self.file_monitor.run()

def test_class_based_parsers() -> None:
    with tempfile.TemporaryDirectory() as temp_d:
        with open(os.path.join(temp_d, "test.json"), "w") as out_f:
            json.dump({"x": 2}, out_f)
        ParserClass().launch()

