from pyramid.httpexceptions import HTTPForbidden

class HTTPTokenNotValid(HTTPForbidden):
    explanation = 'Token is not valid.'

class HTTPServiceNotAllowed(HTTPForbidden):
    explanation = 'OWS service is not allowed.'

class OWSServiceNotFound(Exception):
    pass

class OWSServiceException(Exception):
    pass


