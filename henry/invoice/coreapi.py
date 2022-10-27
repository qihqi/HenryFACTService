from __future__ import division
from __future__ import print_function

import dataclasses
import json
from base64 import b64encode
import time

from decimal import Decimal

from bottle import Bottle, request, abort
import datetime

from henry.base.serialization import json_dumps, decode_str, SerializableData
from henry.base.session_manager import DBContext
from henry.dao.document import Status
from henry.base.common import HenryException

from henry.product.dao import Store, PriceList, create_items_chain
from henry.users.dao import User, Client

from .coreschema import NNota
from .dao import Invoice, NotaExtra, SRINota, SRINotaStatus, CommResult
from .util import compute_access_code, send_remote
from .util import get_or_generate_xml_paths, sri_nota_to_extra, sri_nota_from_nota


__author__ = 'han'


@dataclasses.dataclass
class InvoiceOptions(SerializableData):
    crear_cliente: bool = False
    revisar_producto: bool = False
    incrementar_codigo: bool = False
    usar_decimal: bool = False
    no_alm_id: bool = False


def fix_inv_by_options(dbapi, inv, options):
    inv.items = [x for x in inv.items if x.cant >= 0]
    inv.meta.paid = True

    if options.revisar_producto:  # create producto if not exist
        create_prod_if_not_exist(dbapi, inv)

    for item in inv.items:
        if options.usar_decimal:
            item.cant = Decimal(item.cant)
        else:
            # if not using decimal, means that cant is send as int.
            # treating it as a decimal of 3 decimal places.
            item.cant = Decimal(item.cant) / 1000
            item.prod.cant_mayorista = Decimal(item.prod.cant_mayorista) / 1000

        # this is an effort so that the prod coming from
        # invoice is incomplete. So it attempts so complete it with updated
        # data
        if getattr(
                item.prod,
                'upi',
                None) is None or getattr(
                item.prod,
                'almacen_id',
                None) is None:
            alm_id = item.prod.almacen_id or inv.meta.almacen_id
            if alm_id != 2:
                alm_id = 1
            print(item.prod.prod_id, alm_id)
            newprod = dbapi.search(PriceList, prod_id=item.prod.prod_id,
                                   almacen_id=alm_id)[0]
            item.prod.almacen_id = alm_id
            item.prod.upi = newprod.upi
            item.prod.multiplicador = newprod.multiplicador

    # Get store: if ruc exists get it takes prescendence. Then name, then id.
    # The reason is that id is mysql autoincrement integer and may not be
    # consistent across different servers
    ruc = getattr(inv.meta, 'almacen_ruc', None)
    name = getattr(inv.meta, 'almacen_name', None)

    all_stores = dbapi.search(Store)

    def get_store_by(attr, value):
        temp = [x for x in all_stores if getattr(x, attr) == value]
        if temp:
            return temp[0]
        return None

    alm = None

    # using None as default value is buggy. Because there could
    # be store with store.ruc == None. That's why the if statement is needed
    if ruc:
        alm = get_store_by('ruc', ruc)
    if name and alm is None:
        alm = get_store_by('nombre', name)
    if alm is None:
        alm = get_store_by('almacen_id', inv.meta.almacen_id)

    # FIXME huge hack!!
    if alm is None:
        print('save nota huge hack corpesut')
        if ruc.upper() == 'CORPESUT':
            alm = dbapi.get(3, Store)

    inv.meta.almacen_id = alm.almacen_id
    if options.no_alm_id:
        inv.meta.almacen_id = None
    inv.meta.almacen_name = alm.nombre
    inv.meta.almacen_ruc = alm.ruc
    inv.meta.bodega_id = alm.bodega_id


def parse_invoice_and_options(content_dict):
    options = InvoiceOptions()
    if 'options' in content_dict:
        op = content_dict['options']
        options.merge_from(op)
        del content_dict['options']

    inv = Invoice.deserialize(content_dict)
    return inv, options


def create_prod_if_not_exist(dbapi, inv):
    for i in inv.items:
        alm_id = inv.meta.almacen_id
        if int(alm_id) == 3:
            alm_id = 1
        i.prod.almacen_id = alm_id
        create_items_chain(dbapi, i.prod)


def make_nota_api(
        url_prefix, dbapi, actionlogged,
        invapi, auth_decorator, pedidoapi, workerqueue, jinja_env,
        quinal_ws, corp_ws):
    api = Bottle()
    dbcontext = DBContext(dbapi.session)
    file_manager = invapi.filemanager
    # ########## NOTA ############################

    def alm_id_to_ws(alm_id):
        if alm_id == 1:
            return quinal_ws
        elif alm_id == 3:
            return corp_ws
        else:
            raise HenryException('Almacen id invalid')

    @api.post('{}/nota'.format(url_prefix))
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def create_invoice():
        cont_bytes = request.body.read()
        print(b64encode(cont_bytes))
        json_content = decode_str(cont_bytes)
        if not json_content:
            return ''

        content = json.loads(json_content)
        inv, options = parse_invoice_and_options(content)
        fix_inv_by_options(dbapi, inv, options)
        # always use server's time.
        inv.meta.timestamp = datetime.datetime.now()
        # at this point, inv should no longer change

        if options.crear_cliente:  # create client if not exist
            client = inv.meta.client
            if not dbapi.get(Client, client.codigo):
                dbapi.save(client)

        inv = invapi.save(inv)

        # increment the next invoice's number
        if options.incrementar_codigo:
            user = User(username=inv.meta.user)
            dbapi.update(
                user, {'last_factura': int(inv.meta.codigo) + 1})
        dbapi.db_session.commit()

        return {'codigo': inv.meta.uid}


    @api.put('{}/nota/<uid>'.format(url_prefix))
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def postear_invoice(uid):
        inv = invapi.get_doc(uid)
        invapi.commit(inv)

        nota_extra = dbapi.get(inv.meta.uid, NotaExtra)
        if nota_extra is None:
            nota_extra = NotaExtra()
            nota_extra.uid = inv.meta.uid
            nota_extra.status = Status.COMITTED
            nota_extra.last_change_time = datetime.datetime.now()
            dbapi.create(nota_extra)

        access_code = ''
        ws = None
        sri_nota = None
        if inv.meta.almacen_id in (1, 3):
            sri_nota = dbapi.getone(
                SRINota,
                almacen_ruc=inv.meta.almacen_ruc,
                orig_codigo=inv.meta.codigo)
            ws = alm_id_to_ws(inv.meta.almacen_id)
            if sri_nota is None:
                sri_nota = sri_nota_from_nota(inv, ws)
                dbapi.create(sri_nota)
            access_code = sri_nota.access_code

        if ws is None:
            is_prod = False
        else:
            is_prod = ws.name == 'PRODUCCION'
        status = send_remote(inv, create=True, is_prod=is_prod)
        if sri_nota:
            new_status = SRINotaStatus.CREATED_SENT if status else SRINotaStatus.CREATED
            dbapi.update(sri_nota, {'status': new_status})


        return {'status': inv.meta.status, 'access_code': access_code}

    @api.get(url_prefix + '/nota/<inv_id>')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def get_invoice(inv_id):
        doc = invapi.get_doc(inv_id)
        if doc is None:
            abort(404, 'Nota no encontrado')
            return
        return json_dumps(doc.serialize())

    @api.delete(url_prefix + '/nota/<uid>')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def delete_invoice(uid):
        inv = invapi.get_doc(uid)
        invapi.delete(inv)
        # Save extra information
        nota_extra = dbapi.get(uid, NotaExtra)
        if nota_extra is not None:
            dbapi.update(
                nota_extra,
                {'status': Status.DELETED,
                 'last_change_time': datetime.datetime.now()})

        return {'status': inv.meta.status}

    @api.get('/api/nota_to_print/<uid>')
    @dbcontext
    def get_nota_print(uid):
        sri_nota = dbapi.get(uid, SRINota)
        inv = invapi.get_doc(uid)
        if inv.meta.client.codigo == 'NA':
            inv.meta.client.codigo = '9999999999999'

        ws = alm_id_to_ws(inv.meta.almacen_id)
        if sri_nota is None:
            sri_nota = sri_nota_from_nota(inv, ws)

        store = dbapi.getone(Store, almacen_id=sri_nota.almacen_id)
        extra = sri_nota_to_extra(sri_nota, store, ws)
        temp = jinja_env.get_template('invoice/nota_impreso_matrix.txt')
        return temp.render(inv=inv, extra=extra)

    # this function need to be idenpotent
    @api.put('/api/post_sri_nota/<uid>')
    @dbcontext
    def post_sri_nota(uid):
        return ''
        # NO longer needed. will be done in a cron jb
        sri_nota = dbapi.get(uid, SRINota)
        if sri_nota is None or sri_nota.almacen_id not in (1, 3):
            return {'status': 'failed', 'msg': 'Nota invalida'}

        ws = alm_id_to_ws(sri_nota.almacen_id)
        relpath, signed_path = get_or_generate_xml_paths(
            sri_nota, file_manager, jinja_env, dbapi, ws)

        if sri_nota.status == SRINotaStatus.CREATED:
            fullpath = file_manager.make_fullpath(signed_path)
            with open(fullpath, 'rb') as f:
                xml_content = f.read()
            ws = alm_id_to_ws(sri_nota.almacen_id)

            try:
                ans = ws.validate(xml_content)
            except Exception as e:
                message = str(e)
                result = CommResult(
                    status='failed',
                    request_type='ENVIAR',
                    request_sent=xml_content.decode('utf-8'),
                    response=message,
                    environment=ws.name == 'PRODUCCION',
                    timestamp=datetime.datetime.now(),
                )
                sri_nota.append_comm_result(result, file_manager, dbapi)
                dbapi.update(sri_nota, {
                    'status': SRINotaStatus.VALIDATED_FAILED
                })
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
            time.sleep(0.5)
            try:
                status, text = ws.authorize(sri_nota.access_code)
            except Exception as e:
                message = str(e)
                result = CommResult(
                    status='failed',
                    request_type='AUTORIZAR',
                    request_sent=xml_content.decode('utf-8'),
                    response=message,
                    environment=ws.name == 'PRODUCCION',
                    timestamp=datetime.datetime.now(),
                )
                sri_nota.append_comm_result(result, file_manager, dbapi)
                dbapi.update(sri_nota, {
                    'status': SRINotaStatus.VALIDATED_FAILED
                })
                return {'status': 'failed', 'msg': 'SRI no tiene servicio'}

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

        return {'status': 'success', 'access_code': sri_nota.access_code}

    # ####################### PEDIDO ############################
    @api.post(url_prefix + '/pedido')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def save_pedido():
        json_content = decode_str(request.body.read())
        uid, _ = pedidoapi.save(json_content)
        return {'codigo': uid}

    @api.get(url_prefix + '/pedido/<uid>')
    @actionlogged
    def get_pedido(uid):
        f = pedidoapi.get_doc(uid)
        if f is None:
            abort(404, 'pedido no encontrado')
        return f

    return api


def get_inv_db_instance(session, almacen_id, codigo):
    return session.query(
        NNota.uid, NNota.status, NNota.items_location).filter_by(
        almacen_id=almacen_id, codigo=codigo).first()
