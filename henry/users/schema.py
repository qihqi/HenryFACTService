from sqlalchemy import Column, String, Integer, Boolean, Date
from henry.schema.base import Base

__author__ = 'han'


class NUsuario(Base):
    __tablename__ = 'usuarios'
    username = Column(String(50), primary_key=True)
    password = Column(String(200))
    level = Column('nivel', Integer)
    is_staff = Column(Boolean)
    last_factura = Column(Integer)
    bodega_factura_id = Column(Integer)


class NCliente(Base):
    __tablename__ = 'clientes'
    codigo = Column(String(20), primary_key=True)
    nombres = Column(String(100))
    apellidos = Column(String(100))
    direccion = Column(String(300), nullable=True)
    ciudad = Column(String(50), nullable=False)
    telefono = Column(String(50), nullable=True)
    tipo = Column(String(1))
    cliente_desde = Column(Date)
    email = Column(String(100), nullable=True)
