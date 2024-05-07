"""
This has handlers for pages regarding users and client
"""
import datetime

from bottle import Bottle, request, redirect
from sqlalchemy.exc import IntegrityError

from henry.base.dbapi_rest import bind_dbapi_rest
from henry.base.session_manager import DBContext
from henry.base.dbapi import DBApiGeneric
from henry.base.auth import AuthType
from henry.product.dao import Store
from henry.users.dao import User, Client

from typing import Callable


def make_wsgi_app(dbcontext: DBContext,
                  auth_decorator: AuthType,
                  jinja_env,
                  dbapi: DBApiGeneric,
                  actionlogged: Callable[[Callable],
                                         Callable]):
    w = Bottle()

    # bind apis
    bind_dbapi_rest('/app/api/client', dbapi, Client, w)
    bind_dbapi_rest('/app/api/user', dbapi, User, w)

    @w.get('/app/cliente/<id>')
    @dbcontext
    @auth_decorator(0)
    def modificar_cliente_form(id, message=None):
        client = dbapi.get(id, Client)
        if client is None:
            message = 'Cliente {} no encontrado'.format(id)
        temp = jinja_env.get_template('crear_cliente.html')
        return temp.render(
            client=client,
            message=message,
            action='/app/modificar_cliente',
            button_text='Modificar')

    @w.post('/app/modificar_cliente')
    @dbcontext
    @auth_decorator(0)
    def modificar_cliente():
        clientid = request.forms.codigo
        client = Client(codigo=clientid)
        dbapi.update(client, request.forms)
        redirect('/app/cliente/{}'.format(clientid))

    @w.get('/app/cliente')
    @dbcontext
    @auth_decorator(0)
    def search_cliente_result():
        prefix = request.query.prefijo
        clientes = list(dbapi.search(Client, **{'apellidos-prefix': prefix}))
        temp = jinja_env.get_template('search_cliente_result.html')
        return temp.render(clientes=clientes)

    @w.post('/app/crear_cliente')
    @dbcontext
    @auth_decorator(0)
    def crear_cliente():
        cliente = Client.deserialize(request.forms)
        cliente.cliente_desde = datetime.date.today()
        try:
            dbapi.create(cliente)
            dbapi.db_session.commit()
        except IntegrityError:
            return crear_cliente_form(
                'Cliente con codigo {} ya existe'.format(
                    cliente.codigo))
        return crear_cliente_form(
            'Cliente {} {} creado'.format(
                cliente.apellidos,
                cliente.nombres))

    @w.get('/app/secuencia')
    @dbcontext
    @auth_decorator(1)
    def get_secuencia():
        users = dbapi.search(User)
        temp = jinja_env.get_template('secuencia.html')
        store_dict = {s.almacen_id: s for s in dbapi.search(Store)}
        store_dict[-1] = Store(nombre='Ninguno', next_inv_id=-1)
        return temp.render(users=users, stores=store_dict)

    @w.post('/app/secuencia')
    @dbcontext
    @auth_decorator(1)
    @actionlogged
    def post_secuencia():
        username = request.forms.usuario
        seq = request.forms.secuencia
        user = dbapi.get(username, User)
        dbapi.update(Store(almacen_id=user.bodega_factura_id), 
                     {'next_inv_id': seq})
        redirect('/app/secuencia')

    @w.get('/app/ver_cliente')
    @dbcontext
    @auth_decorator(0)
    def ver_cliente():
        temp = jinja_env.get_template('ver_item.html')
        return temp.render(title='Ver Cliente', baseurl='/app/cliente',
                           apiurl='/api/cliente')

    @w.get('/app/crear_cliente')
    @dbcontext
    @auth_decorator(0)
    def crear_cliente_form(message=None):
        temp = jinja_env.get_template('crear_cliente.html')
        return temp.render(
            client=None,
            message=message,
            action='/app/crear_cliente',
            button_text='Crear')

    bind_dbapi_rest('/app/api/client', dbapi, Client, w)
    return w
