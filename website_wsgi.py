from __future__ import print_function
from beaker.middleware import SessionMiddleware

from henry.accounting.dao import ImageServer, PaymentApi
from henry.advanced import make_experimental_apps
from henry.base.session_manager import SessionManager
from henry.users.web import make_wsgi_app as userwsgi
from henry.accounting.web import make_wsgi_app as accwsgi
from henry.accounting.web import make_wsgi_api as accapi
from henry.product.web import make_wsgi_app as prodapp
from henry.product.web import make_wsgi_api as prod_api_app
from henry.inventory.web import make_inv_wsgi, make_inv_api
from henry.invoice.websites import make_invoice_wsgi
from henry.base.dbapi import DBApiGeneric
from henry.base.fileservice import FileService
from henry.constants import USE_ACCOUNTING_APP, FORWARD_INV, REMOTE_INVOICE_PATH
from henry.config import (BEAKER_SESSION_OPTS, jinja_env, transapi,
                          imagefiles, revisionapi)
from henry.coreconfig import (dbcontext, auth_decorator, sessionmanager,
                              actionlogged, invapi, pedidoapi, transactionapi,
                              sessionfactory, quinal_ws, corp_ws)
from henry.web import webmain as app
from henry.background_sync import sync_api
dbapi = DBApiGeneric(sessionmanager)


forward_transaction = None

invoiceapp = make_invoice_wsgi(
        dbapi, auth_decorator, actionlogged, invapi, pedidoapi, jinja_env,
        workqueue=forward_transaction,
        quinal_ws=quinal_ws,
        corp_ws=corp_ws)
userapp = userwsgi(dbcontext, auth_decorator, jinja_env, dbapi, actionlogged)
invapp = make_inv_wsgi(dbapi, jinja_env, actionlogged, auth_decorator, transapi, revisionapi,
                       revisionapi=None)
invappapi = make_inv_api(dbapi, transapi, auth_decorator, actionlogged, forward_transaction=forward_transaction)
papp = prodapp(dbcontext, auth_decorator, jinja_env, dbapi, imagefiles)
advanced = make_experimental_apps(dbapi, invapi, auth_decorator, jinja_env, transactionapi)

sync_api_obj = sync_api.SyncApi(FileService(sync_api.NEW_LOG_DIR))
create_prod_api = prod_api_app(
    '/app/api',
    sessionmanager=sessionmanager,
    auth_decorator=auth_decorator, dbcontext=dbcontext,
    dbapi=dbapi, inventoryapi=transactionapi, sync_api=sync_api_obj)

app.merge(userapp)
app.merge(invoiceapp)
app.merge(invapp)
app.merge(papp)
app.merge(create_prod_api)
app.merge(invappapi)
app.merge(advanced)

if USE_ACCOUNTING_APP:
    from PIL import Image as PilImage

    def save_image(imgfile, size, filename):
        im = PilImage.open(imgfile)
        if im.size[0] > size[0]:
            im.resize(size)
        im.save(filename)

    imgserver = ImageServer('/app/img', dbapi, imagefiles, save_image)
    paymentapi = PaymentApi(sessionmanager)
    accapp = accwsgi(dbcontext, imgserver,
                     dbapi, paymentapi, jinja_env, auth_decorator, imagefiles, invapi)
    api = accapi(dbapi=dbapi, imgserver=imgserver, dbcontext=dbcontext, paymentapi=paymentapi,
                 auth_decorator=auth_decorator, invapi=invapi)
    app.merge(accapp)
    app.merge(api)

application = SessionMiddleware(app, BEAKER_SESSION_OPTS)
