from collections import defaultdict
from decimal import Decimal
import datetime
import functools
import json
import os
import dataclasses

from henry.base.serialization import parse_iso_date
from henry.base.fileservice import FileService
from henry.base.dbapi import SerializableDB, DBApiGeneric
from henry.base.serialization import json_dumps, SerializableData
from .schema import (
    NBodega,
    NCategory,
    NPriceListLabel,
    NPriceList,
    NItemGroup,
    NItem,
    NStore,
    NProdTag,
    NProdTagContent)
from typing import Dict, Optional, List, Tuple, Union, Iterable, Iterator, Mapping, DefaultDict


@dataclasses.dataclass(init=False)
class Bodega(SerializableDB[NBodega]):
    db_class = NBodega
    id: Optional[int] = None
    nombre: Optional[str] = None
    nivel: Optional[int] = None


@dataclasses.dataclass
class Category(SerializableDB[NCategory]):
    db_class = NCategory
    id: Optional[int] = None
    nombre: Optional[str] = None


@dataclasses.dataclass
class PriceListLabel(SerializableDB[NPriceListLabel]):
    db_class = NPriceListLabel
    uid: Optional[int] = None
    name: Optional[str] = None


@dataclasses.dataclass
class Store(SerializableDB[NStore]):
    db_class = NStore
    almacen_id: Optional[int] = None
    ruc: Optional[str] = None
    nombre: Optional[str] = None
    bodega_id: Optional[int] = None
    address: Optional[str] = None
    next_inv_id: Optional[int] = None


@dataclasses.dataclass
class ProdTag(SerializableDB[NProdTag]):
    db_class = NProdTag
    tag: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None


@dataclasses.dataclass
class ProdTagContent(SerializableDB[NProdTagContent]):
    db_class = NProdTagContent
    uid: Optional[int] = None
    tag: Optional[str] = None
    itemgroup_id: Optional[int] = None


def convert_decimal(x, default=None) -> Optional[Decimal]:
    return default if x is None else Decimal(x)


@dataclasses.dataclass(init=False)
class PriceList(SerializableDB[NPriceList]):
    db_class = NPriceList
    pid: Optional[int] = None
    nombre: Optional[str] = None
    almacen_id: Optional[int] = None
    prod_id: Optional[str] = dataclasses.field(
        default=None,
        metadata={'dict_name': 'codigo'})
    # Using int for money as in number of cents.
    precio1: Optional[int] = None
    precio2: Optional[int] = None
    cant_mayorista: Optional[int] = dataclasses.field(
        default=None,
        metadata={'dict_name': 'threshold'})
    upi: Optional[int] = None
    unidad: Optional[str] = None
    multiplicador: Optional[Decimal] = None


@dataclasses.dataclass(init=False)
class ProdItem(SerializableDB[NItem]):
    db_class = NItem
    uid: Optional[int] = None
    itemgroupid: Optional[int] = None
    prod_id: Optional[str] = None
    multiplier: Optional[Decimal] = None
    unit: Optional[str] = None
    name: Optional[str] = None

    def merge_from(self, the_dict: Dict) -> 'ProdItem':
        super(ProdItem, self).merge_from(the_dict)
        self.multiplier = convert_decimal(self.multiplier, 1)
        return self


@dataclasses.dataclass(init=False)
class ProdItemGroup(SerializableDB[NItemGroup], ):
    db_class = NItemGroup
    uid: Optional[int] = None
    prod_id: Optional[str] = None
    name: Optional[str] = None
    desc: Optional[str] = None
    base_unit: Optional[str] = None
    base_price_usd: Optional[Decimal] = Decimal(0)

    def merge_from(self, the_dict):
        super().merge_from(the_dict)
        self.base_price_usd = convert_decimal(self.base_price_usd, Decimal(0))
        return self


def get_real_prod_id(uid: Optional[str]) -> str:
    if not uid:
        print('Uid is None/empty in get_real_prod_id')
        return ''
    if uid[-1] in ('+', '-'):
        return uid[:-1]
    return uid


def make_itemgroup_from_pricelist(pl: PriceList) -> ProdItemGroup:
    ig = ProdItemGroup(
        prod_id=get_real_prod_id(pl.prod_id),
        name=get_real_prod_id(pl.nombre))
    if pl.multiplicador == 1:
        ig.base_unit = pl.unidad
        if pl.precio1 is not None:
            ig.base_price_usd = Decimal(pl.precio1) / 100
    return ig


def make_item_from_pricelist(pl: PriceList) -> ProdItem:
    i = ProdItem(
        prod_id=pl.prod_id,
        multiplier=pl.multiplicador,
        unit=pl.unidad)
    return i


def create_items_chain(dbapi: DBApiGeneric, pl: PriceList):
    prod_id = get_real_prod_id(pl.prod_id)
    ig = dbapi.getone(ProdItemGroup, prod_id=prod_id)
    if ig is None:
        ig = make_itemgroup_from_pricelist(pl)
        dbapi.create(ig)
    item = dbapi.getone(ProdItem, prod_id=pl.prod_id)
    if item is None:
        item = make_item_from_pricelist(pl)
        item.itemgroupid = ig.uid
        dbapi.create(item)
    pricelist = dbapi.getone(
        PriceList,
        prod_id=pl.prod_id,
        almacen_id=pl.almacen_id)
    if pricelist is None:
        pricelist = PriceList()
        pricelist.merge_from(pl)
        dbapi.create(pricelist)


def quantity_tuple(
        quantities: List[Tuple[int, str]]) -> List[Tuple[int, Decimal]]:
    # quantities should be a list of tuples of bodega_id: quantity
    # with type (int, Decimal)
    # the starting type is (int, str), need to convert str to decimal
    return [(x[0], Decimal(x[1])) for x in quantities]


class InvMovementType(object):
    SALE = 'sale'
    TRANSFER = 'transfer'
    INGRESS = 'ingress'
    EGRESS = 'egress'
    DELETE_SALE = 'delete_sale'
    DELETE_TRANFER = 'delete_tranfer'
    DELETE_INGRESS = 'delete_ingress'
    DELETE_EGRESS = 'delete_egress'
    INITIAL = 'initial_stock'

    @classmethod
    def delete_type(cls, type_):
        return 'delete_' + type_


#  tracks every movement of inventory
@dataclasses.dataclass
class InventoryMovement(SerializableData):
    """
        should have following attributes:
        from_inv_id: (int) id of from bodega
        to_inv_id: (int) id of to bodega
        quantity: (Decimal) positive quantity
        itemgroup: (ProdItemGroup) item in movement
        timestamp: (datetime) time of execution
        type: (str) one of InvMovementType
    """
    from_inv_id: Optional[int] = None
    to_inv_id: Optional[int] = None
    quantity: Optional[Decimal] = None
    itemgroup_id: Optional[int] = None
    prod_id: Optional[str] = None
    timestamp: Optional[datetime.datetime] = None
    type: Optional[str] = None
    reference_id: Optional[str] = None

    def inverse(self):
        self.from_inv_id, self.to_inv_id = self.to_inv_id, self.from_inv_id
        return self


class InventoryApi(object):
    LAST_INIT_DATE_FILE_NAME = '__last_init'

    def __init__(self, fileservice: FileService):
        self.fileservice = fileservice

    @classmethod
    def _year_month(cls, date: Union[datetime.date, datetime.datetime]):
        return '{:04d}-{:02d}'.format(date.year, date.month)

    @classmethod
    def _make_filename(cls, igid: int, date: datetime.date):
        # PROD_ID/yyyy-mm
        return os.path.join(str(igid), cls._year_month(date))

    def save(self, inv_movement: InventoryMovement):
        assert inv_movement.itemgroup_id is not None
        assert inv_movement.timestamp is not None
        path = InventoryApi._make_filename(
            inv_movement.itemgroup_id,
            inv_movement.timestamp.date())
        self.fileservice.append_file(path, json_dumps(inv_movement))
        if inv_movement.type == InvMovementType.INITIAL:
            self._update_init_dates(inv_movement.itemgroup_id, inv_movement.timestamp.date(),
                [inv_movement.to_inv_id]
            )

    def bulk_save(self, trans: Iterable[InventoryMovement]):
        for t in trans:
            self.save(t)

    def _get_init_dates(self, igid):
        init_filename = os.path.join(str(igid), self.LAST_INIT_DATE_FILE_NAME)
        init_filename = self.fileservice.make_fullpath(init_filename)
        if os.path.exists(init_filename):
            old_record = self.fileservice.get_file(init_filename)
            record_obj = json.loads(old_record) # dict of bodega_id to time
            record_obj = {int(key): parse_iso_date(value) for key, value in record_obj.items()}
            return record_obj
        return {}

    def _update_init_dates(self, igid, date, invs):
        record = self._get_init_dates(igid)
        for a in invs:
            record[a] = date
        init_filename = os.path.join(str(igid), self.LAST_INIT_DATE_FILE_NAME)
        self.fileservice.put_file(init_filename, json_dumps(record))
        
    def reset_initial_quantity(self, igid, prod_id, date, inv_to_quantity):
        for inv_id, quantity in inv_to_quantity.items():
            inv_movement = InventoryMovement(
                from_inv_id=-1,
                to_inv_id=inv_id,
                quantity=quantity,
                itemgroup_id=igid,
                prod_id=prod_id,
                timestamp=datetime.datetime.combine(date, datetime.time(23, 59, 59)),
                type=InvMovementType.INITIAL,
            )
            self.save(inv_movement)
        self._update_init_dates(igid, date, inv_to_quantity)

    def list_transactions(
            self, igid: int, start_date: datetime.date, end_date: datetime.date
    ) -> Iterator[InventoryMovement]:
        # start date can be None, but end_date cannot
        if not isinstance(end_date, datetime.date):
            raise ValueError('end_date must be a valid date object')
        if not isinstance(
                start_date,
                datetime.date) and start_date is not None:
            raise ValueError('start_date must be a valid date object')
        if isinstance(end_date, datetime.datetime):
            end_date = end_date.date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
        root = self.fileservice.make_fullpath(str(igid))
        if not os.path.exists(root):
            return
        last_month = InventoryApi._year_month(end_date)
        all_fname = [f for f in os.listdir(root) if f <= last_month]
        if all_fname:
            if start_date is None:
                smallest = min(all_fname)
                year, month = list(map(int, smallest.split('-')))
                start_date = datetime.date(year, month, 1)
            all_fname = sorted(
                f for f in all_fname
                if f >= InventoryApi._year_month(start_date))
            all_fname = list(map(functools.partial(
                os.path.join, str(igid)), all_fname))
            all_fname = sorted(all_fname)

            for fname in all_fname:
                content = []
                for x in self.fileservice.get_file_lines([fname]):
                    if not x.strip():
                        continue
                    try:
                        item = InventoryMovement.deserialize(json.loads(x))
                    except json.decoder.JSONDecodeError:
                        continue
                    if item.timestamp is not None:
                        if start_date <= item.timestamp.date() <= end_date:
                            content.append(item)
                content = sorted(content, key=lambda a: a.timestamp)
                yield from content


    def get_changes(self, igid: int, start_date: datetime.date,
                    end_date: datetime.date) -> Mapping[int, Decimal]:
        transactions = self.list_transactions(igid, start_date, end_date)
        return self.get_changes_from_transactions(transactions)

    def get_changes_from_transactions(self, transactions):
        deltas = defaultdict(Decimal)  # type: DefaultDict[int, Decimal]
        for x in transactions:
            if x.type == InvMovementType.INITIAL:
                if x.quantity:
                    deltas[x.to_inv_id] = x.quantity
            else:
                if x.from_inv_id is not None:
                    if x.quantity:
                        deltas[x.from_inv_id] -= x.quantity
                if x.to_inv_id is not None:
                    if x.quantity:
                        deltas[x.to_inv_id] += x.quantity
        return deltas

    def get_current_quantity_and_change_dates(self, igid: int):
        # get last account
        init_dates = self._get_init_dates(igid)
        start_date = datetime.date(2000, 1, 1)
        if init_dates:
            start_date = min(init_dates.values())
        end_date = datetime.date.today()

        transactions = list(self.list_transactions(igid, start_date, end_date))
        changes = self.get_changes_from_transactions(transactions)
        if transactions:
            last_change = transactions[-1].timestamp
        else:
            last_change = None

        return defaultdict(Decimal, changes), last_change, init_dates 
