from hashlib import sha1

from bottle import request, response, parse_auth

from henry.users.schema import NUsuario


def get_user_info(session, username):
    return session.query(NUsuario).filter_by(username=username).first()


def authenticate(password, userinfo):
    s = sha1()
    s.update(password)
    return s.hexdigest() == userinfo.password


def create_user_dict(userinfo):
    return {
        'username': userinfo.username,
        'status': True,
        'last_factura': userinfo.last_factura,
        'bodega_factura_id': userinfo.bodega_factura_id,
    }


def get_user(r):
    session = r.environ['beaker.session']
    if session is not None:
        return session.get('login_info', None)
    return None


class AuthDecorator:
    def __init__(self, redirect_url, db):
        self.redirect = redirect_url
        self.db = db

    def __call__(self, level):
        def decorator(func):
            def wrapped(*args, **kwargs):
                print request.get_header('Authorization')
                if (self.is_logged_in_by_beaker()
                        or self.is_auth_by_header()):
                    user = get_user(request)['username']
                    db_user = get_user_info(self.db.session, user)
                    if db_user.level >= level:
		        return func(*args, **kwargs)
                    else:
			response.status = 401
			response.set_header('www-authenticate', 'Basic realm="Henry"')
                else:
                    response.status = 401
                    response.set_header('www-authenticate', 'Basic realm="Henry"')
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
            beaker['login_info'] = create_user_dict(userinfo)
            beaker.save()
            return userinfo
        return False

    def is_logged_in_by_beaker(self):
        return get_user(request) is not None
