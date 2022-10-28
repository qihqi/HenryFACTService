import datetime
import dataclasses
from typing import Optional

from henry.base.dbapi import SerializableDB
from henry.users.schema import NUsuario, NCliente

__author__ = 'han'


@dataclasses.dataclass
class User(SerializableDB[NUsuario]):
    db_class = NUsuario
    username: Optional[str] = None
    password: Optional[str] = None
    level: Optional[int] = None
    is_staff: Optional[bool] = None
    last_factura: Optional[int] = None
    bodega_factura_id: Optional[int] = None


@dataclasses.dataclass
class Client(SerializableDB[NCliente]):
    db_class = NCliente
    codigo: Optional[str] = None
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    telefono: Optional[str] = None
    tipo: Optional[str] = None
    cliente_desde: Optional[datetime.date] = None
    email: Optional[str] = None

    @property
    def fullname(self) -> str:
        nombres = self.nombres or ''
        apellidos = self.apellidos or ''
        return apellidos + ' ' + nombres
