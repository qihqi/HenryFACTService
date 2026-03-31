import dataclasses
import datetime
import os
import uuid
from decimal import Decimal

from henry.base.dbapi import SerializableDB
from henry.base.serialization import parse_iso_datetime, SerializableData
from henry.dao.document import MetaItemSet
from henry.product.dao import InvMovementType, InventoryMovement, ProdItem
from henry.product.dao import get_real_prod_id


from .schema import NTransferencia, NRevisionMetadata
from typing import Dict, Optional, List


class TransType(object):
    INGRESS = 'INGRESO'
    TRANSFER = 'TRANSFER'
    EXTERNAL = 'EXTERNA'
    EGRESS = 'EGRESO'

    names = (INGRESS,
             TRANSFER,
             EXTERNAL,
             EGRESS)


@dataclasses.dataclass
class TransMetadata(SerializableDB[NTransferencia]):
    db_class = NTransferencia
    uid: Optional[int] = None
    timestamp: Optional[datetime.datetime] = None
    status: Optional[str] = None
    origin: Optional[int] = None
    dest: Optional[int] = None
    trans_type: Optional[str] = None
    ref: Optional[str] = None
    value: Optional[Decimal] = None
    items_location: Optional[str] = dataclasses.field(default=None, metadata={
        'skip': True})

    @classmethod
    def deserialize(cls, the_dict):
        x = super(cls, TransMetadata).deserialize(the_dict)
        if not isinstance(x.timestamp, datetime.datetime):
            x.timestamp = parse_iso_datetime(x.timestamp)
        return x


def transtype_to_invtype(tipo):
    if tipo == TransType.INGRESS:
        return InvMovementType.INGRESS
    if tipo == TransType.EGRESS:
        return InvMovementType.EGRESS
    if tipo == TransType.EXTERNAL:
        return InvMovementType.EGRESS
    if tipo == TransType.TRANSFER:
        return InvMovementType.TRANSFER


@dataclasses.dataclass
class TransItem(SerializableData):
    prod: ProdItem = dataclasses.field(default_factory=ProdItem)
    cant: Decimal = Decimal(0)

    @classmethod
    def deserialize(cls, the_dict: Dict) -> 'TransItem':
        prod = ProdItem.deserialize(the_dict['prod'])
        cant = Decimal(the_dict['cant'])
        return cls(prod, cant)


@dataclasses.dataclass
class Transferencia(SerializableData, MetaItemSet):
    _metadata_cls = TransMetadata
    meta: TransMetadata
    items: List[TransItem]

    def items_to_transaction(self, dbapi=None):
        assert self.meta is not None, 'Meta is None!'
        for item in self.items:
            # item is ProdItem
            if self.meta.origin == -1:
                type_ = InvMovementType.INGRESS
            elif self.meta.dest == -1:
                type_ = InvMovementType.EGRESS
            else:
                type_ = InvMovementType.TRANSFER

            yield InventoryMovement(
                from_inv_id=self.meta.origin,
                to_inv_id=self.meta.dest,
                quantity=(item.cant * item.prod.multiplier),
                prod_id=get_real_prod_id(item.prod.prod_id),
                itemgroup_id=item.prod.itemgroupid,
                type=type_,
                reference_id=str(self.meta.uid),
            )

    def validate(self):
        if self.meta.trans_type not in (TransType.EXTERNAL, TransType.EGRESS):
            if self.meta.dest is None:
                raise ValueError('dest is none for non external')
        else:
            self.meta.dest = None
        if self.meta.trans_type != TransType.INGRESS:
            if self.meta.origin is None:
                raise ValueError('origin is none for non ingress')
        else:
            self.meta.origin = None

    @property
    def filepath_format(self) -> str:
        path = getattr(self, '_path', None)
        if path is None:
            assert self.meta.timestamp is not None
            self._path = os.path.join(
                self.meta.timestamp.date().isoformat(), uuid.uuid1().hex)
        return self._path

    def update_metadata(self, db_metadata):
        self.meta.status = db_metadata.status


@dataclasses.dataclass
class RevisionMetadata(SerializableDB[NRevisionMetadata]):
    db_class = NRevisionMetadata
    uid: Optional[int] = None
    timestamp: Optional[datetime.datetime] = None
    status: Optional[str] = None
    user: Optional[str] = None
    bodega_id: Optional[int] = None
    items_location: Optional[str] = dataclasses.field(default=None, metadata={
        'skip': True})

    @classmethod
    def deserialize(cls, the_dict):
        x = super(cls, RevisionMetadata).deserialize(the_dict)
        if not isinstance(x.timestamp, datetime.datetime):
            x.timestamp = parse_iso_datetime(x.timestamp)
        return x


@dataclasses.dataclass
class Revision(SerializableData, MetaItemSet):
    _metadata_cls = RevisionMetadata
    meta: RevisionMetadata
    items: List[TransItem]

    def items_to_transaction(self, dbapi=None):
        assert self.meta is not None, 'Meta is None!'
        by_ig_id = {}
        for item in self.items:  # group by itemgroup
            if item.prod.itemgroupid not in by_ig_id:
                by_ig_id[item.prod.itemgroupid] = InventoryMovement(
                    from_inv_id=-1,
                    to_inv_id=self.meta.bodega_id,
                    quantity=(item.cant * item.prod.multiplier),
                    prod_id=get_real_prod_id(item.prod.prod_id),
                    itemgroup_id=item.prod.itemgroupid,
                    type=InvMovementType.INITIAL,
                    reference_id=str(self.meta.uid),
                )
            else:
                by_ig_id[item.prod.itemgroupid].quantity += (
                    item.cant * item.prod.multiplier)

        return by_ig_id.values()

    @property
    def filepath_format(self) -> str:
        path = getattr(self, '_path', None)
        if path is None:
            assert self.meta.timestamp is not None
            self._path = os.path.join(
                self.meta.timestamp.date().isoformat(), uuid.uuid1().hex)
        return self._path

    def update_metadata(self, db_metadata):
        pass

    def validate(self):
        pass
