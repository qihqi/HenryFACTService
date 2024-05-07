from henry.schema.base import Base
from sqlalchemy import (Column, Integer, String,
                        ForeignKey, Numeric, Index, DateTime)
from sqlalchemy.orm import relationship, backref


class NItemGroup(Base):
    """What will replace NProducto"""
    __tablename__ = 'item_groups'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    prod_id = Column(String(20), index=True, unique=True)
    name = Column(String(100))
    desc = Column(String(200))
    base_unit = Column(String(20))
    base_price_usd = Column(Numeric(11, 4))


class NItem(Base):
    __tablename__ = 'items'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    itemgroupid = Column(Integer, ForeignKey(NItemGroup.uid))
    prod_id = Column(String(20), index=True)
    multiplier = Column(Numeric(11, 3))
    unit = Column(String(20))


# TODO deprecate
class NCategory(Base):
    __tablename__ = 'categorias'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100))


class NBodega(Base):
    __tablename__ = 'bodegas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100))
    nivel = Column(Integer)


class NStore(Base):
    __tablename__ = 'almacenes'
    almacen_id = Column('almacen_id', Integer,
                        primary_key=True, autoincrement=True)
    ruc = Column(String(20))
    nombre = Column(String(20))
    bodega_id = Column(Integer)
    address = Column(String(100))
    next_inv_id = Column(Integer)


class NPriceListLabel(Base):
    __tablename__ = 'price_list_labels'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(30))


class NPriceList(Base):
    __tablename__ = 'lista_de_precios'
    pid = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100))  # display name
    almacen_id = Column(Integer)
    prod_id = Column(String(20))
    # Using int for money as in number of cents.
    precio1 = Column(Integer)
    precio2 = Column(Integer)
    cant_mayorista = Column(Integer)
    upi = Column(Integer)
    unidad = Column(String(20))
    multiplicador = Column(Numeric(11, 3))


Index('ix_lista_de_precio_2', NPriceList.almacen_id, NPriceList.prod_id)


class NProdTag(Base):
    __tablename__ = 'product_tags'
    tag = Column(String(30), index=True, primary_key=True)
    description = Column(String(100))
    created_by = Column(String(20))


class NProdTagContent(Base):
    __tablename__ = 'product_tag_contents'
    uid = Column(Integer, primary_key=True)
    tag = Column(String(30), index=True)
    itemgroup_id = Column(Integer, index=True)


class NInventoryRevision(Base):
    __tablename__ = 'revisiones_de_inventario'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    bodega_id = Column(Integer)
    timestamp = Column(DateTime, index=True)
    created_by = Column(String(20))
    status = Column(String(10))
    items = relationship('NInventoryRevisionItem', backref=backref('revision'))


class NInventoryRevisionItem(Base):
    __tablename__ = 'items_de_revisiones'
    uid = Column(Integer, primary_key=True, autoincrement=True)
    revision_id = Column(Integer, ForeignKey(NInventoryRevision.uid))
    prod_id = Column(String(20), index=True)
    inv_cant = Column(Numeric(20, 3))
    real_cant = Column(Numeric(20, 3))
