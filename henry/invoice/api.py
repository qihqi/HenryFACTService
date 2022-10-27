import json
import os
import uuid

from jinja2 import Environment
from bottle import Bottle, request, abort
import datetime

from henry.base.auth import AuthType
from henry.base.dbapi import DBApiGeneric
from henry.base.fileservice import FileService
from henry import constants, common
from henry.product.dao import Store

from henry.base.serialization import json_dumps
from henry.base.session_manager import DBContext
from henry.invoice.dao import SRINota, SRINotaStatus
from henry.dao.document import DocumentApi

from .dao import Invoice
from .util import generate_xml_paths, sri_nota_from_nota

__author__ = 'han'

_ALM_ID_TO_INFO = {
    1: {
        'ruc': constants.RUC,
        'name': constants.NAME,
    },
    3: {
        'ruc': constants.RUC_CORP,
        'name': constants.NAME_CORP,
    },
    99: {
        'ruc': 'RUCRUCRUC',
        'name': 'NAMENAMENAME',
    }
}


class IdType:
    RUC = '04'
    CEDULA = '05'
    CONS_FINAL = '07'


def guess_id_type(client_id):
    if len(client_id) == 10:
        return IdType.CEDULA
    if len(client_id) > 10:
        return IdType.RUC
    return IdType.CONS_FINAL


def make_nota_all(url_prefix: str, dbapi: DBApiGeneric,
                  jinja_env: Environment,
                  file_manager: FileService,
                  invapi: DocumentApi,
                  auth_decorator: AuthType):

    api = Bottle()
    dbcontext = DBContext(dbapi.session)
    # ########## NOTA ############################

    @api.post('{}/remote_nota'.format(url_prefix))
    @dbcontext
    def create_sri_nota():
        msg = request.body.read()
        if not msg:
            return ''
        msg_decoded = common.aes_decrypt(msg).decode('utf-8')
        loaded = json.loads(msg_decoded)

        uid = loaded['uid']
        action = loaded['action']  # create, delete
        inv_json = loaded['inv']
        is_prod = loaded['is_prod']  #
        if action == 'create':
            inv = invapi.get_doc(uid)
            if not inv:
                inv = Invoice.deserialize(inv_json)
                invapi.create(inv)
            sri_nota = dbapi.get(int(uid), SRINota)
            if sri_nota:
                return {'created': False, 'msg': 'ya exist'}
            store = dbapi.get(inv.meta.almacen_id, Store)
            ws = object()
            ws.name = 'PRODUCCION' if is_prod else 'PRUEBA'
            sri_nota = sri_nota_from_nota(inv, store, ws)
            dbapi.create(sri_nota)
            return {'status': 'created'}
        if action == 'delete':
            inv = invapi.get_doc(uid)
            invapi.delete(inv)


    @api.get('{}/remote_nota'.format(url_prefix))
    def get_extended_nota():
        start = request.query.get('start')
        end = request.query.get('end')
        if start is None or end is None:
            abort(400, 'invalid input')
        datestrp = datetime.datetime.strptime
        start_date = datestrp(start, "%Y-%m-%d")
        end_date = datestrp(end, "%Y-%m-%d")
        with dbapi.session:
            res = dbapi.search(SRINota,
                               **{'timestamp_received-gte': start_date,
                                  'timestamp_received-lte': end_date})
        return json_dumps(list(res))

    return api
