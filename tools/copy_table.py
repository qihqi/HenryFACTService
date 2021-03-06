from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from henry.base.dbapi import DBApiGeneric
from henry.base.session_manager import SessionManager
from henry.importation.dao import *

source = 'mysql+mysqldb://root:wolverineaccess@localhost/import?charset=utf8'
dest = 'mysql+mysqldb://root:wolverineaccess@localhost/henry_backup?charset=utf8'
to_copy = [PurchaseItem]

def copy_table(table, dbsource, dbdest):
    for obj in dbsource.search(table):
        try:
            dbdest.create(obj)
        except:
            print 'exception in creating', json_dumps(obj.serialize())


def main():
    dbsource = DBApiGeneric(SessionManager(sessionmaker(bind=create_engine(source, echo=False))))
    dbdest = DBApiGeneric(SessionManager(sessionmaker(bind=create_engine(dest, echo=False))))

    with dbsource.session:
        with dbdest.session:
            for x in to_copy
                copy_table(x, dbsource, dbdest)

def main2():
    # delete purchases
    dbdest = DBApiGeneric(SessionManager(sessionmaker(bind=create_engine(dest, echo=False))))
    with dbdest.session as s:
        for i in range(36):
            if i == 19 or i ==35:
                continue
            print i,
            print s.query(NPurchaseItem).filter_by(purchase_id=i).delete(),
            print s.query(NPurchase).filter_by(uid=i).delete()
main2()
