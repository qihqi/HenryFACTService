"""Convertir unidad de yarda a metro
"""
from henry.coreconfig import sessionmanager, transactionapi
from henry.base.dbapi import DBApiGeneric
from henry.base.serialization import json_dumps
from henry.product.dao import ProdItemGroup, ProdItem, PriceList, InventoryMovement, InvMovementType
from henry.product.schema import NItemGroup, NItem, NPriceList

from typing import Dict, Optional, List
from collections import defaultdict
from dataclasses import dataclass, field
import datetime
from decimal import Decimal

dbapi = DBApiGeneric(sessionmanager)
current_time = datetime.datetime.now()

def get_all_with_yard_unit(dbapi):
    content = dbapi.db_session.query(
            NItem,
            NPriceList).filter(
                NItem.prod_id==NPriceList.prod_id
            ).filter(NItem.unit == 'YARDA')

    return content

@dataclass
class Update:
    igid: int = 0
    prod_id: str = ''
    price: List[NPriceList] = field(default_factory=list)
    cantidad: Optional[defaultdict] = None

METER_IN_YARD = Decimal('0.9144')

APPLY_CHANGES = True


def update_price(update):
    for p in update.price:
        new_p1 = int(round(p.precio1 / METER_IN_YARD))
        new_p2 = int(round(p.precio2 / METER_IN_YARD))
        print('{}:{} cambio precio de {} a {}'.format(
                p.pid,
                p.nombre,
                p.precio1,
                new_p1))
        if APPLY_CHANGES:
            dbapi.update(PriceList(pid=p.pid),
                         {
                             'precio1': new_p1, 
                             'precio2': new_p2, 
                             'unidad': 'METRO',
                          })
            print('price applied')
    for bodega_id, cant in update.cantidad.items():
        inv = InventoryMovement(
            from_inv_id=-1,
            to_inv_id=bodega_id,
            quantity = cant * METER_IN_YARD,
            prod_id = update.prod_id,
            itemgroup_id = update.igid,
            type=InvMovementType.INITIAL,
            reference_id = 'yarda_a_metro',
            timestamp = current_time,
        )
        print(json_dumps(inv))
        if APPLY_CHANGES:
            transactionapi.save(inv)
            print('quant applied')


def main():
    updates = defaultdict(Update)
    with sessionmanager:
        for item, price in get_all_with_yard_unit(dbapi):
            update = updates[item.itemgroupid]
            update.prod_id = price.prod_id
            update.igid = item.itemgroupid
            update.price.append(price)

        for igid, update in updates.items():
            try:
                cantidad=transactionapi.get_current_quantity(igid)
            except:
                print('error in fetching {}'.format(igid))
            update.cantidad = cantidad

        for update in updates.values():
            update_price(update)

if __name__ == '__main__':
    main()


