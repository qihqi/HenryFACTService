from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Numeric, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship, backref
from henry.helpers.serialization import SerializableMixin

Base = declarative_base()


class NProducto(Base):
    __tablename__ = 'productos'
    codigo = Column(String(20), primary_key=True)
    codigo_barra = Column(Integer)
    nombre = Column(String(200))
    categoria_id = Column(Integer)
    contenidos = relationship('NContenido', backref=backref('producto'))


class NContenido(Base):
    __tablename__ = 'contenido_de_bodegas'
    id = Column('id', Integer, primary_key=True, autoincrement=True)
    bodega_id = Column(Integer)
    prod_id = Column(String(20), ForeignKey('productos.codigo'))
    cant = Column(Numeric(23, 3))
    precio = Column(Numeric(20, 2))
    precio2 = Column(Numeric(20, 2))
    cant_mayorista = Column(Integer)


class NVenta(Base):
    __tablename__ = 'notas_de_venta'
    id = Column('id', Integer, primary_key=True)
    vendedor_id = Column('vendedor_id', String(50))
    cliente_id = Column('cliente_id', String(20))
    fecha = Column('fecha', Date)
    bodega_id = Column('bodega_id', Integer)
    items = relationship('NItemVenta', backref=backref('header'))


class NItemVenta(Base):
    __tablename__ = 'items_de_venta'
    id = Column('id', Integer, primary_key=True)
    venta_cod_id = Column('venta_cod_id', Integer, ForeignKey('notas_de_venta.id'))
    num = Column('num', Integer)
    producto_id = Column('producto_id', String(20))
    cantidad = Column('cantidad', Numeric(23, 3))
    nuevo_precio = Column('nuevo_precio', Numeric(20, 2))


class NOrdenDespacho(Base):
    __tablename__ = 'ordenes_de_despacho'
    id = Column('id', Integer, primary_key=True)
    codigo = Column('codigo', Integer)
    vendedor_id = Column('vendedor_id', String(50))
    cliente_id = Column('cliente_id', String(20))
    fecha = Column('fecha', Date)
    bodega_id = Column('bodega_id', Integer)
    pago = Column('pago', String(1))
    precio_modificado = Column('precio_modificado', Boolean)
    total = Column('total', Numeric(23, 3))
    eliminado = Column('eliminado', Boolean)
    items = relationship('NItemDespacho', backref=backref('header'))


class NItemDespacho(Base):
    __tablename__ = 'items_de_despacho'
    id = Column('id', Integer, primary_key=True)
    desp_cod_id = Column('desp_cod_id', Integer, ForeignKey('ordenes_de_despacho.id'))
    num = Column('num', Integer)
    producto_id = Column('producto_id', String(20))
    cantidad = Column('cantidad', Numeric(23, 3))
    precio = Column('precio', Numeric(20, 2))
    precio_modificado = Column('precio_modificado', Boolean)


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
