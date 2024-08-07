"""
Helpers to work around some default view configurations that are not desired.
"""
import contextlib
from typing import TYPE_CHECKING

from cornice import Service as ServiceAutoGetHead
from pyramid.config import Configurator as PyramidConfigurator
from pyramid.predicates import RequestMethodPredicate
from pyramid.util import as_sorted_tuple

if TYPE_CHECKING:
    from typing import Any, Tuple, Union


class Configurator(PyramidConfigurator):
    @contextlib.contextmanager
    def route_prefix_context(self, route_prefix):
        """
        Copy of the original configurator, with tweak for leaving the leading ``/`` of the supplied ``route_prefix``.

        .. fixme:
        .. todo::
            Workaround for https://github.com/Pylons/pyramid/issues/3758
        """
        original_route_prefix = self.route_prefix

        if route_prefix is None:
            route_prefix = ""

        old_route_prefix = self.route_prefix
        if old_route_prefix is None:
            old_route_prefix = ""

        route_prefix = "{}/{}".format(  # pylint: disable=C0209  # format over f-string preserved from original code
            old_route_prefix.rstrip("/"), route_prefix.lstrip("/")
        )

        route_prefix = route_prefix.rstrip("/")   # FIXME: this is the only change 'strip' -> 'rstrip'

        if not route_prefix:
            route_prefix = None

        self.begin()
        try:
            self.route_prefix = route_prefix
            yield

        finally:
            self.route_prefix = original_route_prefix
            self.end()


class NoAutoHeadList(list):
    """
    List that does not allow addition of HTTP HEAD method object references unless allowed once.
    """

    allow_once = False

    def append(self, __object):
        # type: (Union[str, Tuple[str, Any, Any]]) -> None
        method = __object[0] if __object and isinstance(__object, tuple) else __object
        if method == "HEAD":
            if not self.allow_once:
                return
            self.allow_once = False
        super(NoAutoHeadList, self).append(__object)


class ServiceOnlyExplicitGetHead(ServiceAutoGetHead):
    """
    Service that disallow the auto-insertion of HTTP HEAD method view when HTTP GET view is defined.

    This service overrides the default :class:`cornice.Service` in order to avoid auto-insertion of HTTP HEAD view.
    Similarly to :mod:`pyramid`, the view registration assume that HEAD are always wanted when adding GET definitions.
    Because HEAD view can be added explicitly, the class also detects these cases to let them pass as expected.

    Without this patch, all endpoint would otherwise report erroneous HEAD requests in the generated OpenAPI
    specification once HEAD is removed from :attr:`cornice_swagger.CorniceSwagger.ignore_methods`.

    .. seealso::
        - HEAD method removed from ignored methods in :func:`weaver.wps_restapi.api.get_openapi_json`.
        - HEAD method auto-insertion disabled for :mod:`pyramid` in :func:`patch_pyramid_view_no_auto_head_get_method`.
    """

    def __init__(self, *_, **__):
        # type: (*Any, **Any) -> None
        super(ServiceOnlyExplicitGetHead, self).__init__(*_, **__)
        self.defined_methods = NoAutoHeadList()
        self.definitions = NoAutoHeadList()

    def add_view(self, method, view, **kwargs):
        # type: (Union[str, Tuple[str]], Any, **Any) -> None
        method = method.upper()
        if method == "HEAD":  # this is a real HEAD view, add it just this time
            self.definitions.allow_once = True
            self.defined_methods.allow_once = True
        super(ServiceOnlyExplicitGetHead, self).add_view(method, view, **kwargs)


class RequestMethodPredicateNoGetHead(RequestMethodPredicate):
    # pylint: disable=W0231,super-init-not-called  # whole point of this init is to bypass original behavior

    def __init__(self, val, config):  # noqa
        # type: (Union[str, Tuple[str]], Configurator) -> None
        self.val = as_sorted_tuple(val)


def patch_pyramid_view_no_auto_head_get_method(config):
    # type: (Configurator) -> None
    """
    Replace predicate handlers automatically adding HTTP HEAD route/view when HTTP GET are defined by ones that doesn't.
    """
    route_preds = config.get_predlist("route")
    route_preds.sorter.remove("request_method")
    route_preds.add("request_method", RequestMethodPredicateNoGetHead)
    view_preds = config.get_predlist("view")
    view_preds.sorter.remove("request_method")
    view_preds.add("request_method", RequestMethodPredicateNoGetHead)
