"""
based on https://github.com/pypa/warehouse/blob/master/warehouse/config.py
"""

from pyramid.config import Configurator as _Configurator

class Configurator(_Configurator):

    def add_wsgi_middleware(self, middleware, *args, **kwargs):
        middlewares = self.get_settings().setdefault("wsgi.middlewares", [])
        middlewares.append((middleware, args, kwargs))

    def make_wsgi_app(self, *args, **kwargs):
        # Get the WSGI application from the underlying configurator
        app = super(Configurator, self).make_wsgi_app(*args, **kwargs)

        # Look to see if we have any WSGI middlewares configured.
        if "wsgi.middlewares" in self.get_settings():
            for middleware, args, kw in self.get_settings()["wsgi.middlewares"]:
                app = middleware(app, *args, **kw)

        # Finally, return our now wrapped app
        return app
