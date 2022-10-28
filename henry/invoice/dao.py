from curses import ascii
import dataclasses
import datetime
import json
import os
import uuid
from decimal import Decimal
from typing import Optional, Iterator, List, Iterable
from henry.base.serialization import SerializableData
from henry.base.dbapi import SerializableDB, DBApiGeneric
from henry.dao.document import MetaItemSet, Item
from henry.product.dao import InventoryMovement, ProdItem, InvMovementType, get_real_prod_id
from henry.users.dao import Client

from .coreschema import NNota, NNotaExtra, NSRINota
from henry.base.fileservice import FileService

__author__ = 'han'


class PaymentFormat(object):
    CASH = "efectivo"
    CARD = "tarjeta"
    CHECK = "cheque"
    DEPOSIT = "deposito"
    CREDIT = "credito"
    VARIOUS = "varios"
    names = (
        CASH,
        CARD,
        CHECK,
        DEPOSIT,
        CREDIT,
        VARIOUS,
    )


@dataclasses.dataclass
class InvMetadata(SerializableDB[NNota]):
    db_class = NNota
    _pkey_name = 'uid'
    uid: Optional[int] = None
    timestamp: Optional[datetime.datetime] = None
    status: Optional[str] = None

    # this pair should be unique
    codigo: Optional[str] = None
    almacen_id: Optional[int] = None
    almacen_name: Optional[str] = None
    almacen_ruc: Optional[str] = None

    # client_id: Optional[str] = None
    user: Optional[str] = None
    client: Client = Client()
    paid: Optional[bool] = None
    paid_amount: Optional[int] = None
    payment_format: Optional[str] = None

    subtotal: Optional[int] = None
    total: Optional[int] = None
    tax: Optional[int] = None
    retension: Optional[int] = None
    discount: Optional[int] = None
    tax_percent: Optional[int] = None
    discount_percent: Optional[int] = None

    bodega_id: Optional[int] = None
    items_location: Optional[str] = dataclasses.field(default=None, metadata={
        'skip': True})

    def db_instance(self):
        db_instance = super(InvMetadata, self).db_instance()
        db_instance.client_id = self.client.codigo
        return db_instance

    @classmethod
    def from_db_instance(cls, db_instance):
        this = super(InvMetadata, cls).from_db_instance(db_instance)
        this.client = Client()
        this.client.codigo = db_instance.client_id
        return this


@dataclasses.dataclass
class Invoice(SerializableData, MetaItemSet[InvMetadata]):
    _metadata_cls = InvMetadata
    meta: InvMetadata
    items: List[Item]

    def items_to_transaction(self, dbapi) -> Iterator[InventoryMovement]:
        assert self.meta is not None, 'Meta is None!'
        for item in self.items:
            proditem = dbapi.getone(ProdItem, prod_id=item.prod.prod_id)
            # TODO: deprecate use of upi at all
            inv_id = item.prod.upi or self.meta.bodega_id
            if proditem is None:
                print(item.prod.prod_id)
            mult = proditem.multiplier or item.prod.multiplicador
            assert item.cant is not None, 'cant is None'
            assert mult is not None, 'multiplier is None'
            yield InventoryMovement(
                from_inv_id=inv_id,
                to_inv_id=-1,
                quantity=(item.cant * mult),
                prod_id=get_real_prod_id(item.prod.prod_id),
                itemgroup_id=proditem.itemgroupid,
                type=InvMovementType.SALE,
                reference_id=str(self.meta.uid),
            )

    def validate(self):
        if getattr(self.meta, 'codigo', None) is None:
            raise ValueError('codigo cannot be None to save an invoice')

    @property
    def filepath_format(self):
        path = getattr(self, '_path', None)
        if path is None:
            self._path = os.path.join(
                self.meta.timestamp.date().isoformat(), uuid.uuid1().hex)
        return self._path

    def update_metadata(self, db_metadata):
        self.meta.status = db_metadata.status
        self.meta.codigo = db_metadata.codigo
        self.meta.user = db_metadata.user
        self.meta.almacen_id = db_metadata.almacen_id
        self.meta.almacen_name = db_metadata.almacen_name
        self._path = db_metadata.items_location


class SRINotaStatus:
    CREATED = 'created'
    CREATED_SENT = 'sent'
    CREATED_SENT_VALIDATED = 'valid'
    VALIDATED_FAILED = 'vfailed'
    DELETED = 'deleted'
    DELETED_SENT = 'dsent'
    DELETED_SENT_VALIDATED = 'dvalid'
    DELETED_VALIDATED_FAILED = 'dvfailed'


@dataclasses.dataclass
class NotaExtra(SerializableDB[NNotaExtra]):
    db_class = NNotaExtra
    uid: Optional[int] = None
    status: Optional[str] = None
    last_change_time: Optional[datetime.datetime] = None


@dataclasses.dataclass
class CommResult(SerializableData):
    status: str
    request_type: str
    request_sent: str
    response: str
    environment: bool
    timestamp: datetime.datetime


# Use record separator as separator because newline
# might be used already
COMM_SEP = chr(ascii.RS)


@dataclasses.dataclass
class SRINota(SerializableDB[NSRINota]):
    db_class = NSRINota
    uid: Optional[int] = None
    almacen_id: Optional[int] = None
    almacen_ruc: Optional[str] = None
    orig_codigo: Optional[str] = None
    orig_timestamp: Optional[datetime.datetime] = None
    buyer_ruc: Optional[str] = None
    buyer_name: Optional[str] = None

    total: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    access_code: Optional[str] = None

    timestamp_received: Optional[datetime.datetime] = None
    status: Optional[str] = None

    json_inv_location: Optional[str] = None
    xml_inv_location: Optional[str] = None
    xml_inv_signed_location: Optional[str] = None
    all_comm_path: Optional[str] = None

    def load_nota(self, file_manager: FileService) -> Optional[Invoice]:
        if self.json_inv_location is None:
            return None
        inv_text = file_manager.get_file(self.json_inv_location)
        if inv_text is None:
            return None
        inv_dict = json.loads(inv_text)
        inv = Invoice.deserialize(inv_dict)
        return inv

    def load_comm_result(
            self, file_manager: FileService) -> Iterable[CommResult]:
        if self.all_comm_path:
            content = file_manager.get_file(self.all_comm_path)
            if content:
                for line in content.split(COMM_SEP):
                    line = line.strip()
                    if line:
                        yield CommResult.deserialize(json.loads(line))

        return []

    def append_comm_result(
            self,
            comm_result: CommResult,
            file_manager: FileService,
            dbapi: DBApiGeneric):
        if not self.all_comm_path:
            assert self.access_code, 'Access code is None'
            self.all_comm_path = '{}/sri_comms_{}.resp'.format(
                    self.orig_timestamp.date().isoformat(),
                    self.uid)
            dbapi.update(self, {
                'all_comm_path': self.all_comm_path,
            })
        file_manager.append_file(self.all_comm_path,
                                 COMM_SEP + comm_result.to_json())
