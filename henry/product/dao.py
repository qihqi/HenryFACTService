from collections import defaultdict
from decimal import Decimal
import datetime
import functools
import json
import os
import dataclasses

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


#  saves the item stock count at a given time
@dataclasses.dataclass
class InventorySnapshot(SerializableData):
    """
    quantity is a list of tuples (bodega_id, quantity)
    """
    creation_time: Optional[datetime.datetime] = None
    itemgroup_id: Optional[int] = None
    prod_id: Optional[str] = None
    quantity: List[Tuple[int, Decimal]] = dataclasses.field(
        default_factory=lambda: [])
    upto_date: Optional[datetime.date] = None
    last_upto_date: Optional[datetime.date] = None
    last_quantity: List[Tuple[int, Decimal]] = dataclasses.field(
        default_factory=lambda: [])

    # _fields = (
    #     ('creation_time', parse_iso_datetime),
    #     ('itemgroup_id', int),
    #     ('prod_id', str),
    #     ('quantity', quantity_tuple),
    #     ('upto_date', parse_iso_date),
    #     ('last_upto_date', parse_iso_date),
    #     ('last_quantity', quantity_tuple))


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
    SNAPSHOT_FILE_NAME = '__snapshot'

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

    def bulk_save(self, trans: Iterable[InventoryMovement]):
        for t in trans:
            self.save(t)

    def get_past_records(self, igid: int) -> List[InventorySnapshot]:
        snapshotname = os.path.join(str(igid), self.SNAPSHOT_FILE_NAME)
        snapshot_path = self.fileservice.make_fullpath(snapshotname)
        if os.path.exists(snapshot_path):
            records = self.fileservice.get_file(snapshotname)
            if records:
                return list(
                    map(InventorySnapshot.deserialize, json.loads(records)))
        return []

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
        root = self.fileservice.make_fullpath(str(igid))
        last_month = InventoryApi._year_month(end_date)
        all_fname = [f for f in os.listdir(root) if f <= last_month]
        if all_fname:
            if start_date is None:
                smallest = min(all_fname)
                year, month = list(map(int, smallest.split('-')))
                start_date = datetime.date(year, month, 1)
            all_fname = [f for f in all_fname if
                         f >= InventoryApi._year_month(start_date)]
            all_fname = list(map(functools.partial(
                os.path.join, str(igid)), all_fname))
            for x in self.fileservice.get_file_lines(all_fname):
                item = InventoryMovement.deserialize(json.loads(x))
                if item.timestamp is not None:
                    if start_date <= item.timestamp.date() <= end_date:
                        yield item

    def get_changes(self, igid: int, start_date: datetime.date,
                    end_date: datetime.date) -> Mapping[int, Decimal]:
        deltas = defaultdict(Decimal)  # type: DefaultDict[int, Decimal]
        for x in self.list_transactions(igid, start_date, end_date):
            if x.from_inv_id is not None:
                if x.quantity:
                    deltas[x.from_inv_id] -= x.quantity
            if x.to_inv_id is not None:
                if x.quantity:
                    deltas[x.to_inv_id] += x.quantity
        return deltas

    def _write_snapshot(self, igid: int, records):
        snapshotname = os.path.join(str(igid), self.SNAPSHOT_FILE_NAME)
        self.fileservice.put_file(snapshotname, json_dumps(records))

    def take_snapshot_to_date(self, igid: int, end_date: datetime.date):
        new_record, records = self._get_new_snapshot_to_date(igid, end_date)
        records.insert(0, new_record)
        self._write_snapshot(igid, records[:-1])

    def _get_new_snapshot_to_date(self,
                                  igid: int,
                                  end_date: datetime.date) -> Tuple[InventorySnapshot,
                                                                    List[InventorySnapshot]]:
        # get last account
        records = self.get_past_records(igid)
        start_date = datetime.date(2000, 1, 1)
        if records:
            print('HERE')
            print(records)
            # starting date is one day after lasttime!
            assert records[0].upto_date is not None
            start_date = records[0].upto_date + datetime.timedelta(days=1)
        deltas = self.get_changes(igid, start_date, end_date)
        last_quantities = self._get_last_snapshot_quantities(records)

        new_quantities = {}
        for inv_id in set(deltas.keys()) | set(last_quantities.keys()):
            new_quantities[inv_id] = deltas[inv_id] + last_quantities[inv_id]

        new_record = InventorySnapshot()
        new_record.upto_date = end_date
        new_record.creation_time = datetime.datetime.now()
        new_record.quantity = list(new_quantities.items())
        new_record.last_quantity = list(last_quantities.items())
        new_record.last_upto_date = start_date

        return new_record, records

    def _get_last_snapshot_quantities(self, records: List[InventorySnapshot]):
        last_quantities: DefaultDict[int, Decimal] = defaultdict(Decimal)
        if records:
            for inv_id, quantity in records[0].quantity:
                last_quantities[inv_id] = quantity
        return last_quantities

    def get_current_quantity(self, igid: int):
        new_record, _ = self._get_new_snapshot_to_date(
            igid, datetime.date.today())
        return defaultdict(Decimal, new_record.quantity)
