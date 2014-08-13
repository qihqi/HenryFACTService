import itertools
import datetime
from henry.config import new_session
from henry.layer1 import api
from henry.layer1.schema import (
    NVenta, NItemVenta, NOrdenDespacho, NItemDespacho, NCliente)
from henry.helpers.serialization import SerializableMixin

class Venta(SerializableMixin):
    _name = ['cliente',
             'bodega_id',
             'id',
             'items']

    def __init__(self, cliente=None, bodega_id=None, items=None):
        self.id = None
        self.cliente = cliente
        self.bodega_id = bodega_id
        self.items = items # items is una list de tuple (cantidad, codigo)
        self.vendedor_id = None
        self.fecha = None
        self.codigo = None

    def merge_from_db(self, metadata, rows):
        self.id = metadata.id
        self.cliente = metadata.cliente_id
        self.bodega_id = metadata.bodega_id

        def adapt(r):
            c = r.cantidad
            p = Producto().merge_from_cont(r)
            if r.nuevo_precio:
                return c, p, r.nuevo_precio
            else:
                return c, p

        self.items = map(adapt, rows)
        return self

    @classmethod
    def get(cls, venta_id):
        metadata = api.get_nota_de_venta_by_id(venta_id)
        if metadata is None:
            return None
        rows = api.get_items_de_venta_by_id(venta_id, metadata.bodega_id)
        return cls().merge_from_db(metadata, rows)

    @staticmethod
    def save(venta):
        header = NVenta(
            vendedor_id=venta.vendedor_id,
            cliente_id=venta.cliente,
            fecha=datetime.date.today(),
            bodega_id=venta.bodega_id,
        )
        session = new_session()
        session.add(header)
        for num, it in enumerate(venta.items):
            cant = it[0]
            producto = it[1]
            nuevo_p = it[2] if len(it) >= 3 else None
            item = NItemVenta(header=header,
                              num=num,
                              producto_id=producto.codigo,
                              cantidad=cant,
                              nuevo_precio=nuevo_p)
            session.add(item)
        session.commit()
        venta.id = header.id
        venta.fecha = header.fecha
        return venta


class Factura(Venta):

    def merge_from_db(self, metadata, rows):
        self.id = metadata.id
        self.cliente = metadata.cliente_id
        self.bodega_id = metadata.bodega_id

        def adapt(r):
            c = r.cantidad
            p = Producto().merge_from_cont(r)
            real_precio = p.precio1 if c > p.threshold else p.precio2
            if r.precio != real_precio:
                return c, p, r.precio
            else:
                return c, p

        self.items = map(adapt, rows)
        return self

    @classmethod
    def get(cls, codigo):
        metadata = api.get_despacho_by_id(codigo)
        if metadata is None:
            return None
        rows = api.get_items_de_despacho_by_id(metadata.id, metadata.bodega_id)
        return cls().merge_from_db(metadata, rows)

    @classmethod
    def get_with_bodega(cls, codigo, bodega):
        metadata = api.get_despacho_by_bodega(codigo, bodega)
        rows = api.get_items_de_despacho_by_id(metadata.id, metadata.bodega_id)
        return cls().merge_from_db(metadata, rows)


    @staticmethod
    def save(factura):
        header = NOrdenDespacho(
            codigo=factura.codigo,
            vendedor_id=factura.vendedor_id,
            cliente_id=factura.cliente,
            fecha=datetime.date.today(),
            bodega_id=factura.bodega_id,
        )
        session = new_session()
        session.add(header)
        for num, it in enumerate(factura.items):
            cant = it[0]
            producto = it[1]
            item = NItemDespacho(header=header,
                                 num=num,
                                 producto_id=producto.codigo,
                                 cantidad=cant,
                                 precio=producto.precio1,
                                 precio_modificado=False)
            session.add(item)
        session.commit()
        factura.id = header.id
        factura.fecha = header.fecha
        return factura


class Cliente(SerializableMixin, NCliente):
    _name = [
        'apellidos',
        'nombres',
        'codigo',
        'direccion',
        'ciudad'
    ]

    @classmethod
    def get(cls, codigo):
        session = new_session()
        res = session.query(cls).filter(cls.codigo == codigo).first()
        for x in cls._name:
            setattr(res, x, decode(getattr(res, x)))
        return res

    @staticmethod
    def save(cliente):
        session = new_session()
        session.add(cliente)
        session.commit()

    @classmethod
    def search(cls, prefijo):
        session = new_session()
        return list(session.query(cls).filter(cls.apellidos.startswith(prefijo)))
