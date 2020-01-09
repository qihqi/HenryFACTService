import os
def application(env, start_response):
    start_response('200 OK', [('Content-Type','text/html')])
    print(os.system("route | awk '/^default/ { print $2 }"))
    return [b"Hello World"]

