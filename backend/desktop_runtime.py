"""Desktop event-loop helpers."""


def is_expected_client_disconnect(context):
    exc = (context or {}).get("exception")
    return isinstance(exc, ConnectionResetError) and getattr(exc, "winerror", None) == 10054


def install_disconnect_filter(loop):
    previous = loop.get_exception_handler()

    def handler(current_loop, context):
        if is_expected_client_disconnect(context):
            return
        if previous:
            previous(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
