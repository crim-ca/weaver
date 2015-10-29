from pyramid_rpc.jsonrpc import jsonrpc_method

@jsonrpc_method(endpoint='api')
def say_hello(request, name):
    return 'hello, %s!' % name
