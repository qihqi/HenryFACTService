from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from jinja2 import Environment, FileSystemLoader
from henry.helpers.fileservice import FileService
from henry.layer2.productos import ProductApiDB, TransApiDB
from henry.layer2.invoice import InvApiDB, InvApiOld
from henry.layer1.session_manager import SessionManager
from henry.constants import CONN_STRING, INGRESO_PATH, INVOICE_PATH


engine = create_engine(CONN_STRING)
sessionfactory = sessionmaker(bind=engine)
sessionmanger = SessionManager(sessionfactory)
prodapi = ProductApiDB(sessionmanager)

transapi = TransApiDB(sessionfactory(), FileService(INGRESO_PATH), prodapi)
invapi = TransApiDB(sessionfactory(), FileService(INVOICE_PATH), prodapi)
invapi2 = InvApiOld(sessionfactory())


template_paths = ['./templates']
jinja_env = Environment(loader=FileSystemLoader(template_paths))
def id_type(uid):
    if uid == 'NA':
        return '07' # General
    elif len(uid) == 10:
        return '05' # cedula
    elif len(uid) == 13:
        return '04' # RUC
    else:
        return ''
jinja_env.globals.update(id_type=id_type)
