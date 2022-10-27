from sqlalchemy import Column, Integer, DateTime, String, Boolean, Index, Numeric
from henry.schema.base import Base

__author__ = 'han'


class NNota(Base):
    __tablename__ = 'notas'

    uid = Column('id', Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True)
    status = Column(String(10))

    # this pair should be unique
    codigo = Column(String(20))
    almacen_id = Column(Integer)
    almacen_name = Column(String(20))
    almacen_ruc = Column(String(20))

    client_id = Column(String(20))
    user = Column('user_id', String(20))
    paid = Column(Boolean)
    paid_amount = Column(Integer)
    payment_format = Column(String(20))

    subtotal = Column(Integer)  # sum of items
    # amount of money received total = subtotal - discount + iva - retension
    total = Column(Integer)
    tax = Column(Integer)
    retension = Column(Integer)  # (TODO) have to deprecate
    discount = Column(Integer)
    tax_percent = Column(Integer)
    discount_percent = Column(Integer)

    bodega_id = Column(Integer)
    # unix filepath where the items is stored
    items_location = Column(String(200))


Index('ix_notas_2', NNota.almacen_id, NNota.codigo)


class NNotaExtra(Base):
    __tablename__ = 'notas_extras'
    # same as NNota.uid
    uid = Column(Integer, primary_key=True, autoincrement=False)
    status = Column(String(10))
    last_change_time = Column(DateTime)


class NPedidoTemporal(Base):
    __tablename__ = 'pedidos_temporales'
    id = Column(Integer, autoincrement=True, primary_key=True)
    client_lastname = Column(String(20), index=True)
    user = Column(String(20))
    total = Column(Integer)
    timestamp = Column(DateTime)
    status = Column(String(10))
    external_id = Column(Integer)


class NSRINota(Base):
    __tablename__ = 'sri_notas'

    # id, this is the same as NNota.id
    uid = Column(Integer, primary_key=True, autoincrement=False)

    almacen_id = Column(Integer)
    almacen_ruc = Column(String(100))
    orig_codigo = Column(String(100))
    orig_timestamp = Column(DateTime)
    buyer_ruc = Column(String(30))
    buyer_name = Column(String(100))

    total = Column(Numeric(11, 4))
    tax = Column(Numeric(11, 4))
    discount = Column(Numeric(11, 4))
    access_code = Column(String(50))

    # original timestamp == when is this created by client on their time
    timestamp_received = Column(DateTime, index=True)
    # last status of communication
    status = Column(String(20))

    # unix filepath where the items is stored
    json_inv_location = Column(String(200))
    xml_inv_location = Column(String(200))
    xml_inv_signed_location = Column(String(200))

    # path to a json file with communications with remote
    all_comm_path = Column(String(200))
    is_prod = Column(Integer)  # 1 is prod 0 is test
