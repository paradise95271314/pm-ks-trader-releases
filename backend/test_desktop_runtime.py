from desktop_runtime import install_disconnect_filter, is_expected_client_disconnect


class WindowsReset(ConnectionResetError):
    winerror = 10054


def test_windows_client_disconnect_is_expected():
    assert is_expected_client_disconnect({"exception": WindowsReset()})
    assert not is_expected_client_disconnect({"exception": RuntimeError("real failure")})


def test_filter_forwards_real_errors_only():
    forwarded = []

    class Loop:
        def get_exception_handler(self):
            return lambda loop, context: forwarded.append(context)

        def set_exception_handler(self, handler):
            self.handler = handler

    loop = Loop()
    install_disconnect_filter(loop)
    loop.handler(loop, {"exception": WindowsReset()})
    loop.handler(loop, {"exception": RuntimeError("real failure")})
    assert len(forwarded) == 1
