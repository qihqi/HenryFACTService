import datetime

from bottle import request, Bottle, abort, redirect
from henry.config import jinja_env, transapi, prodapi
from henry.layer2.productos import (TransType, Metadata)
from henry.layer2.documents import DocumentCreationRequest
from henry.config import dbcontext

w = Bottle()
web_inventory_webapp = w


@w.get('/app/ingreso/<uid>')
@dbcontext
def get_ingreso(uid):
    trans = transapi.get_doc(uid)
    bodegas = {x.id: x.nombre for x in prodapi.get_bodegas()}
    if trans:
        print trans.serialize()
        temp = jinja_env.get_template('ingreso.html')
        return temp.render(ingreso=trans, bodega_mapping=bodegas)
    else:
        return 'Documento con codigo {} no existe'.format(uid)


@w.get('/app/crear_ingreso')
@dbcontext
def crear_ingreso():
    temp = jinja_env.get_template('crear_ingreso.html')
    bodegas = prodapi.get_bodegas()
    return temp.render(bodegas=bodegas, types=TransType.names)


@w.post('/app/crear_ingreso')
@dbcontext
def post_crear_ingreso():
    meta = Metadata()
    meta.dest = int(request.forms.get('dest'))
    meta.origin = int(request.forms.get('origin'))
    meta.meta_type = request.forms.get('meta_type')
    meta.trans_type = request.forms.get('trans_type')
    meta.timestamp = datetime.datetime.now()
    trans = DocumentCreationRequest(meta)
    for cant, prod_id in zip(
            request.forms.getlist('cant'),
            request.forms.getlist('codigo')):
        if not cant.strip() or not prod_id.strip():
            # skip empty lines
            continue
        try:
            cant = int(cant)
        except ValueError:
            abort(400, 'cantidad debe ser entero positivo')
        if cant < 0:
            abort(400, 'cantidad debe ser entero positivo')
        trans.add(prod_id, cant)
    try:
        transferencia = transapi.save(trans)
    except ValueError as e:
        abort(400, str(e))

    redirect('/app/ingreso/{}'.format(transferencia.meta.uid))
