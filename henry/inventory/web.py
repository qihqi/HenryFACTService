import datetime
import traceback
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

from bottle import Bottle, request, abort, redirect, json_loads

from henry.base.dbapi import DBApiGeneric

from henry.base.auth import AuthType, get_user
from henry.base.common import parse_start_end_date
from henry.base.serialization import json_dumps
from henry.base.session_manager import DBContext
from henry.common import transmetadata_from_form, items_from_form
from henry.dao.document import DocumentApi

from henry.product.dao import Bodega, PriceList, ProdItem

from .dao import TransType, Transferencia, RevisionMetadata, Revision
from .schema import NRevisionMetadata


def make_inv_api(dbapi: DBApiGeneric,
                 transapi: DocumentApi,
                 auth_decorator: AuthType,
                 actionlogged: Callable[[Callable], Callable],
                 forward_transaction):
    api = Bottle()
    dbcontext = DBContext(dbapi.session)

    @api.post('/app/api/ingreso')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def crear_ingreso():
        json_content = request.body.read()
        json_dict = json_loads(json_content)
        ingreso = Transferencia.deserialize(json_dict)
        ingreso = transapi.save(ingreso)
        return {'codigo': ingreso.meta.uid}

    @api.put('/app/api/ingreso/<ingreso_id>')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def postear_ingreso(ingreso_id):
        trans = transapi.get_doc(ingreso_id)
        transapi.commit(trans)
        return {'status': trans.meta.status}

    @api.delete('/app/api/ingreso/<ingreso_id>')
    @dbcontext
    @actionlogged
    def delete_ingreso(ingreso_id):
        trans = transapi.get_doc(ingreso_id)
        transapi.delete(trans)
        return {'status': trans.meta.status}

    @api.get('/app/api/ingreso/<ingreso_id>')
    @dbcontext
    @actionlogged
    def get_ingreso(ingreso_id):
        ing = transapi.get_doc(ingreso_id)
        if ing is None:
            abort(404, 'Ingreso No encontrada')
            return
        return json_dumps(ing.serialize())

    @api.get('/app/api/ingreso')
    @dbcontext
    @actionlogged
    def get_trans_by_date():
        start, end = parse_start_end_date(
            request.query, start_name='start_date', end_name='end_date')
        status = request.query.get('status')
        other_filters = {}
        for x in ('origin', 'dest'):
            t = request.query.get(x)
            if t:
                other_filters[x] = t
        result = transapi.search_metadata_by_date_range(
            start, end, status, other_filters)
        return json_dumps(list(result))

    return api


def make_inv_wsgi(
        dbapi: DBApiGeneric, jinja_env,
        actionlogged: Callable[[Callable], Callable],
        auth_decorator: AuthType, transapi: DocumentApi,
        revapi: DocumentApi,
        revisionapi):  # revisionapi is deprectated
    w = Bottle()
    dbcontext = DBContext(dbapi.session)

    def get_lowest_unit_price_cents(prod):
        candidate_prod_ids = [prod.prod_id]
        if prod.itemgroupid is not None:
            candidate_prod_ids = [
                item.prod_id for item in dbapi.search(ProdItem, itemgroupid=prod.itemgroupid)
                if item.prod_id
            ]
        lowest = None
        for prod_id in candidate_prod_ids:
            prices = dbapi.search(PriceList, prod_id=prod_id)
            item = dbapi.getone(ProdItem, prod_id=prod_id)
            if item is None:
                continue
            multiplier = Decimal(item.multiplier or 1)
            if multiplier == 0:
                continue
            for price in prices:
                if price.precio1 is None:
                    continue
                unit_price = Decimal(price.precio1) / multiplier
                if lowest is None or unit_price < lowest:
                    lowest = unit_price
        if lowest is None:
            return None
        return int(lowest.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    def attach_price_details(doc):
        grand_total = 0
        has_prices = False
        for item in doc.items:
            unit_price_cents = get_lowest_unit_price_cents(item.prod)
            item.unit_price_cents = unit_price_cents
            item.total_price_cents = None
            if unit_price_cents is not None:
                item.total_price_cents = int(
                    (Decimal(unit_price_cents) * item.cant).quantize(
                        Decimal('1'), rounding=ROUND_HALF_UP))
                grand_total += item.total_price_cents
                has_prices = True
        doc.meta.grand_total_price_cents = grand_total
        doc.meta.has_prices = has_prices

    @w.get('/app/ver_ingreso_form')
    @dbcontext
    @auth_decorator(0)
    def ver_ingreso_form():
        return jinja_env.get_template(
            'inventory/ver_ingreso_form.html').render()

    @w.get('/app/ingreso/<uid>')
    @dbcontext
    @auth_decorator(0)
    def get_ingreso(uid):
        trans = transapi.get_doc(uid)
        if not trans:
            return 'Documento con codigo {} no existe'.format(uid)
        temp = jinja_env.get_template('inventory/ingreso.html')
        if trans.meta.origin is not None:
            trans.meta.origin = dbapi.get(trans.meta.origin, Bodega).nombre
        if trans.meta.dest is not None:
            trans.meta.dest = dbapi.get(trans.meta.dest, Bodega).nombre
        attach_price_details(trans)
        return temp.render(ingreso=trans)

    @w.get('/app/crear_ingreso')
    @dbcontext
    @auth_decorator(0)
    def crear_ingreso():
        temp = jinja_env.get_template('inventory/crear_ingreso.html')
        bodegas = dbapi.search(Bodega)
        return temp.render(bodegas=bodegas, externas={},
                           types=TransType.names, revision=False)

    def remove_upi(items):
        for i in items:
            i.prod.upi = None

    @w.post('/app/crear_ingreso')
    @dbcontext
    @auth_decorator(0)
    @actionlogged
    def post_crear_ingreso():
        meta = transmetadata_from_form(request.forms)
        items = items_from_form(dbapi, request.forms)
        # sum((x.cant * (x.prod.base_price_usd or 0) for x in items))
        meta.value = 0
        try:
            transferencia = Transferencia(meta, items)
            transferencia = transapi.save(transferencia)
            redirect('/app/ingreso/{}'.format(transferencia.meta.uid))
        except ValueError as e:
            traceback.print_exc()
            abort(400, str(e))

    @w.get('/app/ingresos_list')
    @dbcontext
    @auth_decorator(0)
    def list_ingress():
        start, end = parse_start_end_date(request.query)
        if not end:
            end = datetime.datetime.now()
        else:
            end = end + datetime.timedelta(days=1) - \
                datetime.timedelta(seconds=1)
        if not start:
            start = end - datetime.timedelta(days=7)
        trans_list = transapi.search_metadata_by_date_range(start, end)
        temp = jinja_env.get_template('inventory/ingresos_list.html')
        bodega = {b.id: b.nombre for b in dbapi.search(Bodega)}
        print(start, end)
        return temp.render(
            trans=trans_list,
            start=start,
            end=end,
            bodega=bodega)

    @w.get('/app/corregir_inventario')
    @dbcontext
    @auth_decorator(2)
    def corregir_inv():
        temp = jinja_env.get_template('inventory/crear_ingreso.html')
        bodegas = dbapi.search(Bodega)
        return temp.render(bodegas=bodegas, externas={},
                           types=TransType.names, revision=True)

    @w.post('/app/corregir_inventario')
    @dbcontext
    @auth_decorator(2)
    @actionlogged
    def post_corregir_ingreso():
        meta = RevisionMetadata()
        meta.timestamp = datetime.datetime.now()
        meta.user = get_user(request)['username']
        meta.bodega_id = int(request.forms.get('dest', -1))
        items = items_from_form(dbapi, request.forms)
        try:
            revision = Revision(meta, items)
            revision = revapi.save(revision)
            revision = revapi.commit(revision)
            redirect('/app/revision/{}'.format(revision.meta.uid))
        except ValueError as e:
            traceback.print_exc()
            abort(400, str(e))

    @w.get('/app/revision/<uid>')
    @dbcontext
    @auth_decorator(0)
    def get_ingreso_web(uid):
        trans = revapi.get_doc(uid)
        if not trans:
            return 'Documento con codigo {} no existe'.format(uid)
        trans.meta.bodega_name = dbapi.get(trans.meta.bodega_id, Bodega).nombre
        attach_price_details(trans)
        temp = jinja_env.get_template('inventory/ingreso.html')
        return temp.render(ingreso=trans, revision=True)

    @w.get('/app/view_revision_form')
    @dbcontext
    @auth_decorator(0)
    def view_revision_form():
        # this doesnt work
        temp = jinja_env.get_template('inventory/view_revision_form.html')
        return temp.render()



    @w.get('/app/list_revision')
    @dbcontext
    @auth_decorator(0)
    def list_revision():
        start, end = parse_start_end_date(request.query)
        if end is None:
            end = datetime.datetime.now()
        if start is None:
            start = end - datetime.timedelta(days=7)

        revisions = dbapi.db_session.query(NRevisionMetadata).filter(
            NRevisionMetadata.timestamp <= end,
            NRevisionMetadata.timestamp >= start)

        temp = jinja_env.get_template('inventory/list_revisions.html')
        return temp.render(revisions=revisions, start=start, end=end)

    @w.get('/app/revisiones')
    @dbcontext
    @auth_decorator(0)
    def revisiones_main():
        temp = jinja_env.get_template('inventory/revisiones.html')
        return temp.render()

    return w
