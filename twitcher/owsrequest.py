class OWSRequest(object):
    """
    :term:`OWSRequest` is wrapper class for :term:`pyramid.request.Request` with additional methods/attributes
    to access OWS parameters.
    """

    def __init__(self, request):
        self._request = request

    @property
    def wrapped(self):
        return self._request

    @property
    def service(self):
        service = None
        if 'service' in self._request.params:
            service = self._request.params['service']
        elif 'SERVICE' in self._request.params:
            service = self._request.params['SERVICE']

        if service:
            service = service.lower()
            
        return service

    @property
    def request(self):
        request = None
        if 'request' in self._request.params:
            request = self._request.params['request']
        elif 'REQUEST' in self._request.params:
            request = self._request.params['REQUEST']

        if request:
            request = request.lower()
            
        return request
    
