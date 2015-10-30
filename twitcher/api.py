from pyramid_rpc.xmlrpc import xmlrpc_method

@xmlrpc_method(endpoint='api')
def say_hello(request, name):
    return 'hello, %s!' % name
