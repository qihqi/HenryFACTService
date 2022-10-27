import sys
import os

from bottle import run, static_file, Bottle
from henry.config import BEAKER_SESSION_OPTS

app = Bottle()


@app.get('/static/<rest:path>')
def static(rest):
    return static_file(rest, root='./static/')

def main():
    global app

    from beaker.middleware import SessionMiddleware
    import cloud_inv
    app.merge(cloud_inv.api)
    app = SessionMiddleware(app, BEAKER_SESSION_OPTS)
    sys.path.append(os.path.dirname(os.path.realpath(__file__)))

    from henry.schema.base import Base
    Base.metadata.create_all(cloud_inv.engine)
    print('created')

    host, port = '0.0.0.0', 8081
    if len(sys.argv) > 1:
        url = sys.argv[1]
        host, port = url.split(':')
        port = int(port)
    for r in app.app.routes:
        print(r.method, r.rule)
    run(app, host=host, debug=True, port=port)
    return 'http://localhost:8081'


if __name__ == '__main__':
    main()
