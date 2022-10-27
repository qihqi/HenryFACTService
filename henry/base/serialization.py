import dataclasses
import datetime
import decimal
import json
import unicodedata
import re
from typing import Dict, Tuple, TypeVar, Type, Any, Callable, Union, Sequence
from henry.base.interface import SerializableInterface


def json_dumps(content) -> str:
    return json.dumps(content, cls=ModelEncoder)


def parse_iso_datetime(datestring: str) -> datetime.datetime:
    parts = list(map(int, re.split('[^\\d]', datestring)))
    if len(parts) > 7:
        parts = parts[:7]
    return datetime.datetime(*parts)  # type: ignore


def parse_iso_date(datestring: str) -> datetime.date:
    parts = list(map(int, datestring.split('-')))[:3]
    return datetime.date(*parts)  # type: ignore


class ModelEncoder(json.JSONEncoder):

    def __init__(self, use_int_repr=False, decimal_places=2, *args, **kwargs):
        super(ModelEncoder, self).__init__(*args, **kwargs)
        self.use_int_repr = use_int_repr
        self.decimal_places = decimal_places

    def default(self, obj):
        if hasattr(obj, 'serialize'):
            return obj.serialize()
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super(ModelEncoder, self).default(obj)


def deserialize(cls, input_obj):
    if input_obj is None:
        return None
    if dataclasses.is_dataclass(cls):
        kwargs = {}
        for field in cls.__dataclass_fields__.values():  # type: ignore
            metadata = field.metadata
            dictname = metadata.get('dict_name', field.name)
            potential_val = input_obj.get(dictname)
            # if potential_val is str, and have a from_str constructor:
            if isinstance(potential_val, str) and 'from_str' in metadata:
                from_str = metadata['from_str']
                kwargs[field.name] = from_str(potential_val)
            else:
                kwargs[field.name] = deserialize(field.type, potential_val)
        return cls(**kwargs)

    arg_types = getattr(cls, '__args__', None)
    origin_types = getattr(cls, '__origin__', None)
    if origin_types is not None:
        if origin_types == Union:  # Optiona[T] == union[t, none]
            return deserialize(arg_types[0], input_obj)

        if issubclass(origin_types, Sequence):
            return [deserialize(arg_types[0], i) for i in input_obj]

    if isinstance(input_obj, cls):  # for int, float, str
        return input_obj

    if isinstance(input_obj, str) and cls == datetime.datetime:
        return parse_iso_datetime(input_obj)

    if isinstance(input_obj, str) and cls == datetime.date:
        return parse_iso_date(input_obj)

    return cls(input_obj)  # this should catch Decinmal


T = TypeVar('T', bound='SerializableData')


class SerializableData(SerializableInterface):
    """Meant to be subclassed by a class with @dataclass decorator.

    Adds methods to support converting to / from dicts
    """

    def __init__(self, **kwargs):
        self.merge_from(kwargs)

    def merge_from(self: T, obj: Any) -> T:
        fieldcopy(src=obj, dest=self,
                  fields=self.__dataclass_fields__.keys())  # type: ignore
        return self

    def serialize(self) -> Dict[str, Any]:
        """Respects renaming or / and skipping."""
        res = {}
        for field in self.__dataclass_fields__.values():  # type: ignore
            if field.metadata.get('skip', False):
                continue
            dictname = field.metadata.get('dict_name', field.name)
            res[dictname] = getattr(self, field.name)
        return res

    @classmethod
    def deserialize(cls: Type[T], dict_input: Dict[str, Any]) -> T:
        return deserialize(cls, dict_input)

    def to_json(self) -> str:
        return json_dumps(self.serialize())


class SerializableMixin(object):
    _name = ()  # type: Tuple

    def merge_from(self, obj):
        for key in self._name:
            their = getattr(obj, key, None)
            if their is None and hasattr(obj, 'get'):  # merge from dict
                their = obj.get(key, None)
            mine = getattr(self, key, None)
            if isinstance(their, bytes):
                their = decode_str(their)
            setattr(self, key, their or mine)  # defaults to theirs
        return self

    def serialize(self):
        return SerializableMixin._serialize_helper(self, self._name)

    @classmethod
    def deserialize(cls, dict_input):
        return cls().merge_from(dict_input)

    @staticmethod
    def _serialize_helper(obj, names):
        return {
            name: getattr(
                obj,
                name) for name in names if getattr(
                obj,
                name,
                None) is not None}

    def to_json(self):
        return json_dumps(self.serialize())


def mkgetter(obj: Any) -> Callable:
    if hasattr(obj, 'get'):
        return obj.get
    return obj.__getattribute__


def decode_str(strobj: bytes) -> str:
    try:
        # Assumes utf8 as catchall
        return strobj.decode('utf-8')
    except UnicodeError:
        return strobj.decode('latin1')


def mksetter(obj: Any) -> Callable:
    if hasattr(obj, 'get'):
        return obj.__setitem__
    return obj.__setattr__


def fieldcopy(src, dest, fields):
    srcgetter = mkgetter(src)
    destsetter = mksetter(dest)
    for f in fields:
        try:
            value = srcgetter(f)
            if isinstance(value, bytes):
                value = decode_str(value)
            destsetter(f, value)
        except BaseException:
            pass
