from henry.coreconfig import sessionmanager, invapi, WS_PROD
from henry.base.dbapi import DBApiGeneric
from henry.invoice.dao import InvMetadata, SRINota
from henry.invoice.util import sri_nota_from_nota
dbapi = DBApiGeneric(sessionmanager)

data = [
    (1, 933805),
    (1, 933923),
    (1, 933929),
]
with sessionmanager:
    for (a, c) in data:
        meta = dbapi.getone(InvMetadata, almacen_id=a, codigo=c)
        print('create', a, c)
        n = invapi.get_doc(meta.uid)
        if dbapi.get(n.meta.uid, SRINota):
            print('ya existe')
            continue
        s = sri_nota_from_nota(n, WS_PROD)
        dbapi.create(s)
        print('done')


    
