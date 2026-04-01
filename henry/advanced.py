from __future__ import print_function
from builtins import object
from collections import defaultdict
import datetime
from bottle import Bottle, request, abort, redirect

from sqlalchemy import desc

from henry.accounting.acct_schema import ObjType, NComment
from henry.base.session_manager import DBContext
from henry.product.dao import ProdItemGroup, ProdItem, PriceList, Category, Store, Bodega, InvMovementType
from henry.invoice.coreschema import NNota
from henry.dao.document import Item
from henry.invoice.dao import PaymentFormat
from henry.base.common import parse_start_end_date_with_default


def make_experimental_apps(dbapi, invapi, auth_decorator, jinja_env, transactionapi):
    w = Bottle()
    dbcontext = DBContext(dbapi.session)

    @w.get('/app/adv')
    @auth_decorator(0)
    def index():
        return '''
        <p><a href="/app/pricelist">Price List</a></p>
        <p><a href="/app/vendidos_por_categoria_form">Por Categoria</a></p>
        <p><a href="/app/ver_transacciones">Transacciones</a></p>
        <p><a href="/app/ver_ventas">Ventas</a></p>
        <p><a href="/app/adv/view_cant">Ver cantidades</a></p>
        '''

    @w.get('/app/adv/view_cant')
    @dbcontext
    def view_cant():
        prod_ids = request.query.get('prod_ids', "")
        prods = []
        prod_ids_not_found = []
        if prod_ids:
            for prod_id in prod_ids.split(","):
                prod_id = prod_id.strip()
                prod_detail = dbapi.getone(ProdItemGroup, prod_id=prod_id)
                if prod_detail:
                    count, last_change_date, last_revision_date_dict = transactionapi.get_current_quantity_and_change_dates(prod_detail.uid)
                    if -1 in count:
                        del count[-1]
                    end = last_change_date.date() if last_change_date else datetime.date.today()
                    start = end - datetime.timedelta(days=30)
                    inv_change_link = f'/app/adv/view_inventory_change/{prod_detail.prod_id}?start={start.isoformat()}&end={end.isoformat()}'
                    prods.append((prod_detail, count, last_change_date, last_revision_date_dict, inv_change_link))
                else:
                    prod_ids_not_found.append(prod_id)
        # print(prods)
        invs = dbapi.search(Bodega)
        inv_id_to_name = {b.id: b.nombre for b in invs}
        inv_id_to_name[-1] = '-'
        inv_id_to_name[None] = '-'
        temp = jinja_env.get_template('view_cant.html')
        return temp.render(
            prod_ids=prod_ids, 
            prods=prods, 
            prod_ids_not_found=prod_ids_not_found, 
            inv_id_to_name=inv_id_to_name)

    @w.get('/app/adv/view_inventory_change/<prod_id>')
    @dbcontext
    def view_inventory_change(prod_id):
        today = datetime.date.today()
        start, end = parse_start_end_date_with_default(
            request.query, today - datetime.timedelta(days=7), today)
        prod_detail = dbapi.getone(ProdItemGroup, prod_id=prod_id)
        msg = ''
        trans = []
        changes = {}
        invs = dbapi.search(Bodega)
        id_to_name = {b.id: b.nombre for b in invs}
        id_to_name[-1] = '-'
        id_to_name[None] = '-'

        def get_ref_link(type_, id_):
            if type_ == InvMovementType.INITIAL:
                if id_ is not None:
                    return f'/app/revision/{id_}'
                else:
                    return '' 
            if type_ == InvMovementType.SALE:
                return f'/app/nota/{id_}'
            if type_ == InvMovementType.DELETE_SALE:
                return f'/app/nota/{id_}'
            if type_ in (InvMovementType.INGRESS,
                         InvMovementType.EGRESS,
                         InvMovementType.TRANSFER,
                         InvMovementType.DELETE_EGRESS,
                         InvMovementType.DELETE_INGRESS,
                         InvMovementType.DELETE_TRANFER):
                return f'/app/ingreso/{id_}'

        def translate_type(type_):
            if type_ == InvMovementType.INITIAL:
                return 'initial'
            if type_ == InvMovementType.SALE:
                return 'venta'
            if type_ == InvMovementType.DELETE_SALE:
                return 'borrar_venta'
            if type_ == InvMovementType.INGRESS:
                return 'ingreso'
            if type_ == InvMovementType.EGRESS:
                return 'egreso'
            if type_ == InvMovementType.TRANSFER:
                return 'transferencia'
            if type_ == InvMovementType.DELETE_EGRESS:
                return 'borrar_egreso'
            if type_ == InvMovementType.DELETE_INGRESS:
                return 'borrar_ingreso'
            if type_ == InvMovementType.DELETE_TRANFER:
                return 'borrar_tranferencia'
            
        if prod_detail is None:
            msg = f'Codigo {prod_id} no encontrado'
        else:
            trans = list(transactionapi.list_transactions(prod_detail.uid, start, end))
            # add helper info to help render
            for t in trans:
                t.to_inv_name = id_to_name[t.to_inv_id]
                t.from_inv_name = id_to_name[t.from_inv_id]
                t.ref_link = get_ref_link(t.type, t.reference_id)
                t.type = translate_type(t.type)
            changes = transactionapi.get_changes_from_transactions(trans)
            changes = [(id_to_name[b], q) for b, q in changes.items() if b not in (None, -1)]

        temp = jinja_env.get_template('view_inventory_change.html')
        return temp.render(
            start=start,
            end=end,
            prod=prod_detail, 
            inv_movements=trans,
            changes=changes,
            msg = msg,
            )

    class Prod(object):
        def __init__(self):
            self.prod = None
            self.items = []
            self.pricelist = []

    @w.get('/app/adv/items')
    @dbcontext
    def show_items():
        all_itemgroups = dbapi.search(ProdItemGroup)
        items = dbapi.search(ProdItem)
        pricelist = dbapi.search(PriceList)

        by_id = defaultdict(Prod)

        def get_id(x):
            if x[-1] == '+':
                return x[:-1].upper()
            return x.upper()

        for x in all_itemgroups:
            by_id[get_id(x.prod_id)].prod = x
        for x in items:
            by_id[get_id(x.prod_id)].items.append(x)
        for x in pricelist:
            by_id[get_id(x.prod_id)].pricelist.append(x)

        temp = jinja_env.get_template('items.html')
        return temp.render(all=by_id)

    @w.get('/app/pricelist')
    @dbcontext
    @auth_decorator(2)
    def get_price_list():
        almacen_id = request.query.get('almacen_id')
        prefix = request.query.get('prefix')
        if not prefix:
            prefix = ''
        if almacen_id is None:
            abort(400, 'input almacen_id')
        prods = dbapi.search(PriceList, **{'nombre-prefix': prefix,
                                           'almacen_id': almacen_id})
        temp = jinja_env.get_template('buscar_precios.html')
        return temp.render(prods=prods)

    @w.get('/app/vendidos_por_categoria_form')
    @dbcontext
    @auth_decorator(2)
    def vendidos_por_categoria_form():
        temp = jinja_env.get_template('vendidos_por_categoria_form.html')
        categorias = dbapi.search(Category)
        return temp.render(cat=categorias)

    def full_invoice_items(api, start_date, end_date):
        invs = api.search_metadata_by_date_range(start_date, end_date)
        for inv in invs:
            fullinv = invapi.get_doc_from_file(inv.items_location)
            if fullinv is None:
                continue
            for x in fullinv.items:
                yield inv, x

    @w.get('/app/ver_ventas')
    @dbcontext
    @auth_decorator(2)
    def sale_by_product():
        today = datetime.datetime.now()
        start, end = parse_start_end_date_with_default(
            request.query, today - datetime.timedelta(days=7), today)
        alm_id = int(request.query.get('almacen_id', 1))
        almacen = dbapi.get(alm_id, Store)

        prods_sale = defaultdict(Item)
        for inv, x in full_invoice_items(invapi, start, end):
            if inv.almacen_id != almacen.almacen_id:
                continue
            obj = prods_sale[x.prod.prod_id]
            obj.prod = x.prod
            if obj.cant:
                obj.cant += x.cant
            else:
                obj.cant = x.cant
        temp = jinja_env.get_template('ver_ventas_por_prod.html')
        values = sorted(list(prods_sale.values()),
                        key=lambda x: -x.cant * x.prod.precio1)
        for x in values:
            print(x.serialize())
        return temp.render(items=values, start=start, end=end,
                           almacen=almacen.nombre,
                           almacenes=dbapi.search(Store))

    @w.get('/app/edit_note/<uid>')
    @dbcontext
    @auth_decorator(2)
    def edit_note(uid):
        note = dbapi.db_session.query(NNota).filter_by(uid=uid).first()
        temp = jinja_env.get_template('edit_note.html')
        return temp.render(note=note)

    @w.post('/app/edit_note/<uid>')
    @dbcontext
    @auth_decorator(2)
    def post_edit_note(uid):
        values = dict(request.forms)
        if values['payment_format'] not in PaymentFormat.names:
            return 'invalid payment format'
        for key in ('subtotal', 'total', 'tax', 'discount'):
            if key in values:
                values[key] = int(values[key])
        dbapi.db_session.query(NNota).filter_by(uid=uid).update(
            values)
        redirect(request.url)

    @w.get('/app/ver_comentarios')
    @dbcontext
    @auth_decorator(2)
    def ver_comentarios():
        today = datetime.datetime.now() + datetime.timedelta(days=1)
        start, end = parse_start_end_date_with_default(
            request.query, today - datetime.timedelta(days=7), today)
        comments = list(dbapi.db_session.query(NComment).filter(
            NComment.timestamp >= start, NComment.timestamp < end).order_by(
            desc(NComment.timestamp)))
        obj_template = {
            ObjType.CHECK: '/app/ver_cheque/{}',
            ObjType.INV: '/app/nota/{}',
            ObjType.TRANS: '/app/ingreso/{}',
        }
        for c in comments:
            c.url = obj_template[c.objtype].format(c.objid)

        temp = jinja_env.get_template('ver_comentarios.html')
        return temp.render(comentarios=comments, start=start, end=end)

    return w
