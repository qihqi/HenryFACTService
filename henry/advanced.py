from __future__ import print_function
from builtins import object
from collections import defaultdict
import datetime
from bottle import Bottle, request, abort, redirect

from sqlalchemy import desc

from henry.accounting.acct_schema import ObjType, NComment
from henry.base.session_manager import DBContext
from henry.product.dao import ProdItemGroup, ProdItem, PriceList, Category, Store
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
        <a href="/app/pricelist">Price List</a>
        <a href="/app/vendidos_por_categoria_form">Por Categoria</a>
        <a href="/app/ver_transacciones">Transacciones</a>
        <a href="/app/ver_ventas">Ventas</a>
        '''

    @w.get('/app/adv/view_cant')
    @dbcontext
    def view_cant():
        prods = []
        for i, x in enumerate(dbapi.search(ProdItemGroup)):
            #TODO(remove)
            if i > 100:
                break
            prods.append((x, transactionapi.get_current_quantity(x.uid)))
        # print(prods)
        temp = jinja_env.get_template('view_cant.html')
        return temp.render(prods=prods)

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
