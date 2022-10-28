import json
import os
import uuid

from jinja2 import Environment
from bottle import Bottle, request, abort
import datetime
from sqlalchemy import and_

from henry.base.auth import AuthType
from henry.base.dbapi import DBApiGeneric
from henry.base.fileservice import FileService
from henry import constants, common
from henry.product.dao import Store

from henry.base.serialization import json_dumps
from henry.base.session_manager import DBContext
from henry.invoice.dao import SRINota, SRINotaStatus, CommResult
from henry.invoice.coreschema import NSRINota
from henry.dao.document import DocumentApi
from henry.base.common import HenryException
from henry.coreconfig import WS_TEST, WS_PROD

from .dao import Invoice
from .util import generate_xml_paths, sri_nota_from_nota, WsEnvironment
from .util import (
    get_or_generate_xml_paths,
    generate_xml_paths,
    sri_nota_to_extra,
    sri_nota_from_nota,
    REMAP_SRI_STATUS
)

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


def make_nota_all(prefix: str, dbapi: DBApiGeneric,
                  jinja_env: Environment,
                  file_manager: FileService,
                  invapi: DocumentApi,
                  auth_decorator: AuthType,
                  quinal_ws: WsEnvironment,
                  corp_ws: WsEnvironment):

    def alm_id_to_ws(alm_id):
        if alm_id == 1:
            return quinal_ws
        elif alm_id == 3:
            return corp_ws
        else:
            raise HenryException('Almacen id invalid')

    api = Bottle()
    dbcontext = DBContext(dbapi.session)
    # ########## NOTA ############################

    @api.post('{}/remote_nota'.format(prefix))
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
            inv = Invoice.deserialize(inv_json)
            sri_nota = dbapi.getone(
                    SRINota,
                    almacen_id=inv.meta.almacen_id,
                    orig_codigo=inv.meta.codigo
            )
            if sri_nota:
                return {'created': False, 'msg': 'ya exist'}
            inv.meta.uid = None
            invapi.save(inv)
            store = dbapi.get(inv.meta.almacen_id, Store)
            ws = object()
            name = 'PRODUCCION' if is_prod else 'PRUEBA'
            code = 2 if is_prod else 1
            ws = WsEnvironment(name, str(code), '', '')
            sri_nota = sri_nota_from_nota(inv, ws)
            sri_nota.is_prod = is_prod
            dbapi.create(sri_nota)
            return {'status': 'created'}
        if action == 'delete':
            inv = invapi.get_doc(uid)
            invapi.delete(inv)

    @api.get('{}/remote_nota/<uid>'.format(prefix))
    @dbcontext
    def get_single_nota(uid):
        sri_nota = dbapi.get(uid, SRINota)
        json_inv = json.loads(
            file_manager.get_file(sri_nota.json_inv_location))
        xml1 = None
        if sri_nota.xml_inv_signed_location:
            xml1 = file_manager.get_file(sri_nota.xml_inv_signed_location)
        comm_results = reversed(list(
            sri_nota.load_comm_result(file_manager)))
        temp = jinja_env.get_template('invoice/sri_nota_full2.html')
        sri_nota.status = REMAP_SRI_STATUS.get(
            sri_nota.status or '', 'INVALIDO')
        return temp.render(
            nota=sri_nota, json=json.dumps(json_inv, indent=4),
            xml1=xml1, comm_results=comm_results)

    @api.get('{}/nota_to_print/<uid>'.format(prefix))
    @dbcontext
    @auth_decorator(0)
    def get_nota_print(uid):
        sri_nota = dbapi.get(uid, SRINota)
        inv = invapi.get_doc(uid)
        if sri_nota is None:
            ws = alm_id_to_ws(inv.meta.almacen_id)
            sri_nota = sri_nota_from_nota(inv, ws)
        store = dbapi.getone(Store, almacen_id=sri_nota.almacen_id)
        ws = alm_id_to_ws(sri_nota.almacen_id)
        extra = sri_nota_to_extra(sri_nota, store, ws)
        temp = jinja_env.get_template('invoice/nota_impreso.html')
        response.headers['Cache-Control'] = 'no-cache'
        return temp.render(inv=inv, extra=extra)

    @api.post('{}/api/gen_xml/<uid>'.format(prefix))
    @dbcontext
    def gen_xml(uid):
        uid = int(uid)
        sri_nota = dbapi.get(uid, SRINota)
        is_prod = bool(request.forms.get('is_prod', 'false') == 'true')
        if is_prod:
            ws = WS_PROD
        else:
            ws = WS_TEST
        relpath, signed_path = generate_xml_paths(
            sri_nota, file_manager, jinja_env, dbapi, ws)

        return {'result': signed_path}

    @api.put('{}/api/mark_remote_nota_as_valid/<uid>'.format(prefix))
    @dbcontext
    def mark_remote_nota_as_valid(uid):
        uid = int(uid)
        sri_nota = dbapi.get(uid, SRINota)
        result = CommResult(
            status='success',
            request_type='AUTORIZAR',
            request_sent='',
            response='Marcado manualmente como autorizado',
            environment=True,
            timestamp=datetime.datetime.now(),
        )
        sri_nota.append_comm_result(result, file_manager, dbapi)
        dbapi.update(sri_nota, {
            'status': SRINotaStatus.CREATED_SENT_VALIDATED
        })

        return {'status': 'success'}

    @api.post('{}/validate_remote'.format(prefix))
    @dbcontext
    def validate_nota():
        uid = request.forms.get('uid')
        sri_nota = dbapi.get(uid, SRINota)
        is_prod = bool(request.forms.get('is_prod', 'false') == 'true')
        if is_prod:
            ws = WS_PROD
        else:
            ws = WS_TEST
        xml, xml_signed = get_or_generate_xml_paths(
            sri_nota, file_manager, jinja_env, dbapi, ws)
        fullpath = file_manager.make_fullpath(xml_signed)
        with open(fullpath, 'rb') as f:
            xml_content = f.read()
        try:
            ans = ws.validate(xml_content)
        except ConnectionError:
            return {'status': 'failed', 'msg': 'SRI no tiene servicio'}

        result = CommResult(
            status='success',
            request_type='ENVIAR',
            request_sent=xml_content.decode('utf-8'),
            response=str(ans),
            environment=ws.name == 'PRODUCCION',
            timestamp=datetime.datetime.now(),
        )
        sri_nota.append_comm_result(result, file_manager, dbapi)
        dbapi.update(sri_nota, {
            'status': SRINotaStatus.CREATED_SENT
        })
        return {'status': 'success'}

    @api.post('{}/authorize_remote'.format(prefix))
    @dbcontext
    def autorize_remote():
        uid = request.forms.get('uid')
        is_prod = bool(request.forms.get('is_prod', 'false') == 'true')
        sri_nota = dbapi.get(uid, SRINota)
        if is_prod:
            ws = WS_PROD
        else:
            ws = WS_TEST

        status, text = ws.authorize(sri_nota.access_code)

        result = CommResult(
            status=status,
            request_type='AUTORIZAR',
            request_sent=sri_nota.access_code,
            response=text,
            environment=ws.name == 'PRODUCCION',
            timestamp=datetime.datetime.now(),
        )
        sri_nota.append_comm_result(result, file_manager, dbapi)
        dbapi.update(sri_nota, {
            'status': status,
        })
        return {'status': 'success'}

    @api.get('{}/view_nota'.format(prefix))
    @dbcontext
    def view_nota():
        start = request.query.get('start')
        end = request.query.get('end')
        temp = jinja_env.get_template('invoice/sync_invoices_form2.html')
        stores = dbapi.search(Store, **{'ruc-ne': None})
        all_status = [
            dict(key='all', name='TODOS'),
            dict(key=SRINotaStatus.CREATED, name='CREADO'),
            dict(key=SRINotaStatus.CREATED_SENT, name='ENVIADO'),
            dict(key=SRINotaStatus.CREATED_SENT_VALIDATED, name='AUTORIZADO'),
            dict(key='invalid', name='INVALIDO'),
        ]
        if start is not None and end is not None:
            datestrp = datetime.datetime.strptime
            start_date = datestrp(start, "%Y-%m-%d")
            end_date = datestrp(end, "%Y-%m-%d") + datetime.timedelta(days=1)
            almacen_ruc = request.query.get('almacen_ruc')
            status = request.query.get('status', 'todos')
            query = dbapi.db_session.query(NSRINota).filter(
                and_(NSRINota.timestamp_received >= start_date,
                     NSRINota.timestamp_received < end_date,
                     NSRINota.almacen_ruc == almacen_ruc))
            valid_status = (
                SRINotaStatus.CREATED,
                SRINotaStatus.CREATED_SENT,
                SRINotaStatus.CREATED_SENT_VALIDATED)
            if status in valid_status:
                query = query.filter(NSRINota.status == status)
            elif status == 'invalid':
                query = query.filter(NSRINota.status.not_in(valid_status))
            res = list(map(SRINota.from_db_instance, query.all()))
            for sri_nota in res:
                sri_nota.status = REMAP_SRI_STATUS.get(
                    sri_nota.status or '', 'INVALIDO')

        else:
            res = []
        return temp.render(rows=res, stores=stores,
                           status=all_status, old_query=request.query)


    @api.get('{}/modificar_almacenes'.format(prefix))
    @dbcontext
    @auth_decorator(0)
    def mod_alm_direccion():
        almacenes = dbapi.search(Store, **{'ruc-ne': None})
        temp = jinja_env.get_template('prod/modificar_almacen.html')
        return temp.render(almacenes=almacenes, url_prefix=prefix)


    @api.post('{}/modificar_almacen/<uid>'.format(prefix))
    @dbcontext
    @auth_decorator(0)
    def mod_alm_post(uid):
        almacenes = dbapi.search(Store, **{'ruc-ne': None})
        uid = int(uid)
        alm = [a for a in almacenes if a.almacen_id == uid]
        temp = jinja_env.get_template('prod/modificar_almacen.html')
        if not alm:
            return temp.render(almacenes=almacenes,
                               url_prefix=prefix,
                               message='Almacen con id {} no existe'.format(uid))
        alm = alm[0]

        dir = request.forms.get('address')
        name = request.forms.get('nombre')
        update_dict = {}
        if name:
            update_dict['nombre'] = name
        if dir:
            update_dict['address'] = dir
        dbapi.update(alm, update_dict)
        return temp.render(almacenes=almacenes,
                           url_prefix=prefix,
                           message='Cambios Guardado')

    return api
