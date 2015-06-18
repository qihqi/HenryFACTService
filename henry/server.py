import sys
import os

from bottle import run, static_file, Bottle

from henry.config import BEAKER_SESSION_OPTS
from henry.website.web_inventory import web_inventory_webapp
from henry.website.accounting import accounting_webapp
from henry.authentication import app as authapp

app = Bottle()


@app.get('/static/<rest:path>')
def static(rest):
    return static_file(rest, root='./static/')


app.merge(web_inventory_webapp)
app.merge(accounting_webapp)

def main():
    global app
    from henry.api_endpoints import api
    from beaker.middleware import SessionMiddleware
    app.merge(api)
    app = SessionMiddleware(app, BEAKER_SESSION_OPTS)
    sys.path.append(os.path.dirname(os.path.realpath(__file__)))
    from henry.base.schema import Base
    from henry.config import engine
    Base.metadata.create_all(engine)
    host, port = '0.0.0.0', 8080
    if len(sys.argv) > 1:
        url = sys.argv[1]
        host, port = url.split(':')
        port = int(port)
    run(app, host=host, debug=True, port=port)
    return 'http://localhost:8080'


if __name__ == '__main__':
    main()
