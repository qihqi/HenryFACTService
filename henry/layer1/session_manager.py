import traceback
from bottle import HTTPResponse


class SessionManager(object):

    def __init__(self, session_factory):
        self._session = None
        self._factory = session_factory

    def __enter__(self):
        self._session = self._factory()
        return self._session

    def __exit__(self, type, value, stacktrace):
        if type is None:
            self._session.commit()
            return True
        else:
            if type is not HTTPResponse:
                traceback.print_exception(type, value, stacktrace)
                self._session.rollback()
            else:
                self._session.commit()
            return False

    @property
    def session(self):
        return self._session
