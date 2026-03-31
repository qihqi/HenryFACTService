from bottle import Bottle, abort, request
from henry.base.auth import get_user_info, authenticate, create_user_dict
from henry.base.dbapi import DBApiGeneric
from henry.base.serialization import json_dumps
from henry.base.session_manager import DBContext

from .dao import Client
from typing import Callable

__author__ = 'han'


def make_client_coreapi(
        url_prefix: str, dbapi: DBApiGeneric,
        actionlogged: Callable[[Callable], Callable]):

    api = Bottle()
    dbcontext = DBContext(dbapi.session)

    @api.get(url_prefix + '/cliente/<codigo>')
    @dbcontext
    @actionlogged
    def get_cliente(codigo):
        client = dbapi.get(codigo, Client)
        if client is None:
            abort(404, 'cliente no encontrado')
        return json_dumps(client.serialize())

    @api.get(url_prefix + '/cliente')
    @dbcontext
    @actionlogged
    def search_client():
        prefijo = request.query.prefijo
        if prefijo:
            return json_dumps(list(
                dbapi.search(Client, **{'apellidos-prefix': prefijo})))
        abort(400)

    @api.post(url_prefix + '/authenticate')
    def post_authenticate():
        beaker = request.environ.get('beaker.session')
        login_info = beaker.get('login_info')
        if login_info is not None:  # user is already logged in
            return login_info

        username = request.forms.get('username')
        password = request.forms.get('password')
        with dbapi.session as session:
            info = get_user_info(session, username)
            if info is None:
                return {'status': False, 'message': 'Usuario no encontrado'}
            if authenticate(password, info):
                data = create_user_dict(session, info)
                beaker['login_info'] = data
                beaker.save()
                return data
            return {'status': False, 'message': 'Clave equivocada'}

    return api
