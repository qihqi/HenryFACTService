from hashlib import sha1

import bottle
from bottle import request, response, parse_auth
from henry.users.schema import NUsuario
from henry.product.schema import NStore

from typing import Any, Dict, Optional, Callable
from sqlalchemy.orm.session import Session
from henry.base.session_manager import SessionManager


def get_user_info(session: Session, username: str) -> Optional[NUsuario]:
    return session.query(NUsuario).filter_by(username=username).first()


def authenticate(password: str, userinfo: NUsuario):
    s = sha1()
    s.update(password.encode('utf-8'))
    return s.hexdigest() == userinfo.password


def create_user_dict(session, userinfo: NUsuario) -> Dict[str, Any]:
    store = session.query(NStore).filter_by(almacen_id=userinfo.bodega_factura_id).first()
    return {
        'username': userinfo.username,
        'status': True,
        'last_factura': store.next_inv_id,
        'bodega_factura_id': userinfo.bodega_factura_id,
    }


def get_user(r: bottle.LocalRequest) -> Optional[str]:
    session = r.environ['beaker.session']
    if session is not None:
        return session.get('login_info', None)
    return None


AuthType = Callable[[int], Callable[[Callable], Callable]]


class AuthDecorator(object):
    def __init__(self, redirect_url: str, db: SessionManager):
        self.redirect = redirect_url
        self.db = db

    def __call__(self, level: int):
        def decorator(func):
            def wrapped(*args, **kwargs):
                print(request.get_header('Authorization'))
                if (self.is_logged_in_by_beaker()
                        or self.is_auth_by_header()):
                    user = get_user(request)['username']
                    db_user = get_user_info(self.db.session, user)
                    if db_user.level >= level:
                        return func(*args, **kwargs)
                    else:
                        response.status = 401
                        response.set_header(
                            'www-authenticate', 'Basic realm="Henry"')
                else:
                    response.status = 401
                    response.set_header(
                        'www-authenticate', 'Basic realm="Henry"')
            return wrapped

        return decorator

    def is_auth_by_header(self):
        header = request.get_header('Authorization')
        if header is None:
            return False
        pair = parse_auth(header)
        if pair is None:
            return False
        user, passwd = pair
        userinfo = get_user_info(self.db.session, user)
        if userinfo is None:
            return False
        if authenticate(passwd, userinfo):
            beaker = request.environ.get('beaker.session')
            beaker['login_info'] = create_user_dict(self.db.session, userinfo)
            beaker.save()
            return userinfo
        return False

    def is_logged_in_by_beaker(self) -> bool:
        return get_user(request) is not None
