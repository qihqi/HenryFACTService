import json
import os
import barcode
from bottle import Bottle, request, redirect
from decimal import Decimal

from .dao import (Product, ProdItem, ProdItemGroup, PriceList,
                  PriceListLabel, Inventory, ProdCount, Store, Bodega)
from henry.base.dbapi_rest import bind_dbapi_rest


def convert_to_cent(dec):
    if not isinstance(dec, Decimal):
        dec = Decimal(dec)
    return int(dec * 100)


def create_full_item_from_dict(dbapi, content):
    """
        input format:
        {
            "prod" : {prod_id, name, desc, base_unit}< - information on item group
            "items": [multiplier, unit
                "prices": {
                   "display_name":
                   "price1":
                   "price2":
                   "cant":
                }, ...
                ]<- information on items requires multiplier be distinct
        }
        must be called within dbcontext
    """
    itemgroup = ProdItemGroup()
    itemgroup.merge_from(content['prod'])

    itemgroupid = dbapi.create(itemgroup)

    prod = Product()
    prod.nombre = itemgroup.name
    prod.codigo = itemgroup.prod_id
    dbapi.create(prod)

    items = {}
    inventories = {}
    allstores = {x.almacen_id: x for x in dbapi.search(Store)}

    conts = {}
    for bod in dbapi.search(Bodega):
        if bod.id == -1:
            continue
        contenido = ProdCount()
        contenido.bodega_id = bod.id
        contenido.prod_id = itemgroup.prod_id
        contenido.cant = 0
        contenido.precio = 0
        contenido.precio2 = 0
        cid = dbapi.create(contenido)
        conts[bod.id] = cid

    for item in content['items']:
        prices = item['prices']
        del item['prices']
        i = ProdItem()
        i.merge_from(item)
        i.itemgroupid = itemgroupid
        if i.multiplier == 1:
            i.prod_id = itemgroup.prod_id
        elif i.multiplier > 1:
            i.prod_id = itemgroup.prod_id + '+'
        elif i.multiplier < 1:
            i.prod_id = itemgroup.prod_id + '-'

        item_id = dbapi.create(i)
        items[i.unit] = i

        # create bodega
        invs = {}
        for bod in dbapi.search(Bodega):
            if bod.id == -1:
                continue
            inv = Inventory()
            inv.item_id = item_id
            inv.bodega_id = bod.id
            inv.cant = 0
            inv_id = dbapi.create(inv)
            invs[bod.id] = inv

        # create prices
        for alm_id, p in prices.items():
            price = PriceList()
            price.nombre = p['display_name']
            price.precio1 = int(float(p['price1']) * 100)
            price.precio2 = int(float(p['price2']) * 100)
            price.cant_mayorista = p['cant']
            price.prod_id = i.prod_id
            price.unidad = i.unit
            price.almacen_id = int(alm_id)
            bodid = allstores[price.almacen_id].bodega_id
            price.upi = conts[bodid]
            price.multiplicador = i.multiplier
            dbapi.create(price)


def validate_full_item(content, dbapi):
    prod_id = content['prod']['prod_id']
    if dbapi.get(prod_id, Product) is not None:
        return False, 'Codigo ya existe'
    if len([x for x in content['items'] if int(x['multiplier']) == 1]) != 1:
        return False, 'Debe haber un unidad con multiplicador 1'
    all_mult = set()
    for i in content['items']:
        if i['multiplier'] in all_mult:
            return False, 'Todos las unidades debe tener multiplicador distintos'
        all_mult.add(i['multiplier'])
    return True, ''


def make_wsgi_api(prefix, sessionmanager, dbcontext, auth_decorator, dbapi):
    app = Bottle()

    @app.post('/{}/item_full'.format(prefix))
    @dbcontext
    @auth_decorator
    def create_item_full():
        '''
            input format:
            {
                "prod" : {prod_id, name, desc, base_unit}< - information on item group
                "items": [{multiplier}, {unit}<- information on items requires multiplier be distinct
                "prices": [{unit, almacen_id, display_name, price1, price2, cant}]
                "new_unit": []
            }
        '''

        content = request.body.read()
        content = json.loads(content)
        valid, message = validate_full_item(content, dbapi)
        if not valid:
            return {'status': 'failure', 'msg': message}
        create_full_item_from_dict(dbapi, content)
        sessionmanager.session.commit()
        return {'status': 'success'}

    bind_dbapi_rest('/app/api/pricelist', dbapi, PriceList, app)
    bind_dbapi_rest('/app/api/itemgroup', dbapi, ProdItemGroup, app)
    bind_dbapi_rest('/app/api/item', dbapi, ProdItem, app)
    return app


def make_wsgi_app(dbcontext, auth_decorator, jinja_env, dbapi, imagefiles):
    w = Bottle()

    @w.get('/app/ver_lista_precio')
    @dbcontext
    @auth_decorator
    def ver_lista_precio():
        almacen_id = int(request.query.get('almacen_id', 1))
        prefix = request.query.get('prefix', None)
        if prefix:
            prods = dbapi.search(PriceList, **{'nombre-prefix': prefix,
                                               'almacen_id': almacen_id})
        else:
            prods = []
        temp = jinja_env.get_template('prod/ver_lista_precio.html')
        return temp.render(
            prods=prods, stores=dbapi.search(Store), prefix=prefix,
            almacen_name=dbapi.get(almacen_id, Store).nombre)

    @w.get('/app/barcode_form')
    @dbcontext
    @auth_decorator
    def barcode_form():
        msg = request.query.msg
        temp = jinja_env.get_template('prod/barcode_form.html')
        return temp.render(alms=dbapi.search(Store), msg=msg)

    @w.get('/app/barcode')
    @dbcontext
    @auth_decorator
    def get_barcode():
        prod_id = request.query.get('prod_id')
        almacen_id = request.query.get('almacen_id')
        quantity = int(request.query.get('quantity', 1))

        prod = dbapi.getone(PriceList, prod_id=prod_id, almacen_id=almacen_id)

        if quantity > 1000:
            redirect('/app/barcode_form?msg=cantidad+muy+grande')

        if not prod:
            redirect('/app/barcode_form?msg=producto+no+existe')

        encoded_string = '{:03d}{:09d}'.format(quantity, prod.pid)
        bar = barcode.EAN13(encoded_string)
        filename = bar.ean + '.svg'
        path = imagefiles.make_fullpath(filename)
        if not os.path.exists(path):
            with open(path, 'w') as barcode_file:
                bar.write(barcode_file)
        url = '/app/img/{}'.format(filename)

        column = 5
        row = 9
        price = int(prod.precio1 * quantity * Decimal('1.12') + Decimal('0.5'))

        temp = jinja_env.get_template('prod/barcode.html')
        return temp.render(url=url, row=row, column=column, prodname=prod.nombre, price=price)
    return w