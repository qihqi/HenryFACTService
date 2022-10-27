import os
from beaker.middleware import SessionMiddleware
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from henry.base.auth import AuthDecorator
from henry.base.dbapi import DBApiGeneric
from henry.base.fileservice import FileService
from henry.base.session_manager import DBContext
from henry.constants import (
        TRANSACTION_PATH,
        DATA_ROOT,
        INVOICE_PATH,
        REMOTE_INVOICE_PATH,
        CLOUD_CONN_STRING,
        LOGIN_URL,
        ENV)
from henry.sale_records.dao import InvMovementManager
from henry.product.dao import InventoryApi
from henry.invoice.api import make_nota_all
from henry.invoice.dao import Invoice
from henry.dao.document import DocumentApi

from henry.config import jinja_env
from henry.base.session_manager import SessionManager, DBContext
from henry.coreconfig import (
    BEAKER_SESSION_OPTS, actionlogged, quinal_ws, corp_ws
)


engine = create_engine(CLOUD_CONN_STRING, pool_recycle=3600, echo=False)
sessionfactory = sessionmaker(bind=engine)
sessionmanager = SessionManager(sessionfactory)
# this is a decorator
dbcontext = DBContext(sessionmanager)
dbapi = DBApiGeneric(sessionmanager)

# for testing, make auth_decorator do nothing
def auth_decorator(x):
    return (lambda y: y)


if ENV == 'prod':
    auth_decorator = AuthDecorator(LOGIN_URL, sessionmanager)

fileservice = FileService(REMOTE_INVOICE_PATH)
inventoryapi = InventoryApi(FileService(TRANSACTION_PATH))
invmomanager = InvMovementManager(dbapi, fileservice, inventoryapi)
invapi = DocumentApi(sessionmanager, fileservice,
                     inventoryapi, object_cls=Invoice)


api = make_nota_all('/sync', dbapi=dbapi,
                    jinja_env=jinja_env,
                    invapi=invapi,
                    file_manager=fileservice,
                    auth_decorator=auth_decorator,
                    quinal_ws=quinal_ws,
                    corp_ws=corp_ws)

application = SessionMiddleware(api, BEAKER_SESSION_OPTS)
