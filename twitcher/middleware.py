class DummyMiddleware(object):
    def __init__(self, app, **kwargs):
        """Initialize the Dummy Middleware"""
        self.app = app
        #config = config or {}

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)
