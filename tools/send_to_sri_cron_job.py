import os
import time
import datetime
from henry import constants
from henry.base.dbapi import DBApiGeneric
from henry.invoice.util import send_sri_by_date_range
from henry.base.fileservice import FileService
from henry.coreconfig import WS_PROD, WS_TEST
from henry.config import jinja_env
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from henry.base.session_manager import SessionManager, DBContext

def alm_id_to_ws(alm_id):
    if alm_id == 1:
        is_prod = constants.QUINAL_WS_PROD
    elif alm_id == 3:
        is_prod = constants.CORP_WS_PROD
    else:
        return None

    if is_prod:
        return WS_PROD
    else:
        return WS_TEST


def main():
    engine = create_engine(constants.CLOUD_CONN_STRING, pool_recycle=3600, echo=False)
    sessionfactory = sessionmaker(bind=engine)
    sessionmanager = SessionManager(sessionfactory)
    dbapi = DBApiGeneric(sessionmanager)
    file_manager = FileService(os.path.join(constants.DATA_ROOT, 'inv_logs'))
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=1)
    with dbapi.sm:
        send_sri_by_date_range(
            start, end,
            alm_id_to_ws=alm_id_to_ws,
            dbapi=dbapi,
            jinja_env=jinja_env,
            file_manager=file_manager)


if __name__ == '__main__':
    main()

