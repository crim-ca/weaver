try:
    import contextlib
except ImportError:
    import six
    raise_exc = None
    if six.PY2:
        try:
            import contextlib2  # noqa
            contextlib = contextlib2
        except ImportError as exc:
            raise_exc = exc
    else:
        raise_exc = ImportError("contextlib should be available directly")
    if raise_exc is not None:
        raise ImportError("could not resolve contextlib [{!r}]".format(raise_exc))
