import itertools
import datetime
from henry.config import new_session
from henry.layer1.schema import NProducto, NContenido
from henry.helpers.serialization import SerializableMixin, decode

class Producto(SerializableMixin):
    _name = ['nombre',
             'codigo',
             'precio1',
             'precio2',
             'threshold',
             'cantidad']

    def __init__(self,
                 codigo=None,
                 nombre=None,
                 precio1=None,
                 precio2=None,
                 threshold=None,
                 cantidad=None,
                 almacen_id=None,
                 bodega_id=None):
        self.codigo = codigo
        self.nombre = nombre
        self.almacen_id = almacen_id
        self.precio1 = precio1
        self.precio2 = precio2
        self.threshold = threshold
        self.bodega_id = bodega_id
        self.cantidad = cantidad


class ProductApiDB:

    _PROD_KEYS = [
        NProducto.codigo, 
        NProducto.nombre,
    ]
    _PROD_PRICE_KEYS = [
        NContenido.bodega_id.label('almacen_id'),
        NContenido.precio.label('precio1'),
        NContenido.precio2,
        NContenido.cant_mayorista.label('threshold')
    ]
    _PROD_CANT_KEYS = [
        NContenido.cant,
        NContenido.bodega_id,
    ]

    def __init__(self, db_session):
        self._prod_name_cache = {}
        self._prod_price_cache = {}
        self.db_session = db_session

    def get_producto(self, prod_id, almacen_id=None, bodega_id=None):
        p = Producto()
        query_item = ProductApiDB._PROD_KEYS[:]
        filter_items = [NProducto.codigo == prod_id]
        if almacen_id is not None:
            query_item.extend(ProductApiDB._PROD_PRICE_KEYS)
            filter_items.append(NContenido.prod_id == NProducto.codigo)
            filter_items.append(NContenido.bodega_id == almacen_id)
        item = self.db_session.query(*query_item)
        for f in filter_items:
            item = item.filter(f)
        return Producto().merge_from(item.first())

    def search_producto(self, prefix, almacen_id=None, bodega_id=None):
        query_items = ProductApiDB._PROD_KEYS[:]
        filters = [NProducto.nombre.startswith(prefix)]
        if almacen_id is not None:
            query_items.extend(ProductApiDB._PROD_PRICE_KEYS)
            filters.append(NContenido.prod_id == NProducto.codigo)
            filters.append(NContenido.bodega_id == almacen_id)
        result_proxy = self.db_session.query(*query_items)

        for f in filters:
            result_proxy = result_proxy.filter(f)
        for r in result_proxy:
            yield Producto().merge_from(r)

    def save(self, prod):
        p = self._construct_db_instance(prod)
        self.db_session.add(p)
        self.db_session.commit()

    def save_batch(self, prods):
        for p in prods:
            x = self._construct_db_instance(p)
            self.db_session.add(x)
        self.db_session.commit()

    def _construct_db_instance(self, prod):
        p = NProducto(
                codigo=prod.codigo,
                nombre=prod.nombre, 
                categoria=prod.categoria)
        if prod.almacen_id:
            c = NContenido(
                    bodega_id=prod.almacen_id,
                    precio=prod.precio1,
                    precio2=prod.precio2,
                    )
            p.contenidos.add(c)
        return p
