from logging_setup import TeeLogger, read_log


class GbkTerminal:
    encoding = "gbk"

    def __init__(self):
        self.values = []

    def write(self, value):
        value.encode(self.encoding)
        self.values.append(value)

    def flush(self):
        return None


def test_cent_symbol_never_crashes_gbk_terminal(tmp_path):
    path = tmp_path / "api.log"
    logger = TeeLogger(path, GbkTerminal())

    logger.write("profit=94.0¢\n")
    logger.flush()

    assert "profit=94.0¢" in read_log(path)


def test_log_file_failure_does_not_crash_caller(tmp_path):
    logger = TeeLogger(tmp_path / "api.log")
    logger.log_file.close()

    assert logger.write("trading must continue") == len("trading must continue")
    logger.flush()
