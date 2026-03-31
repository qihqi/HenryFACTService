import datetime
from decimal import Decimal
from bottle import abort

__author__ = 'han'

from typing import Mapping, Tuple, Optional


class HenryException(Exception):
    pass


def parse_iso(date_string: str) -> datetime.datetime:
    return datetime.datetime.strptime(date_string, '%Y-%m-%d')


def parse_start_end_date(forms: Mapping[str, str],
                         start_name: str = 'start', end_name: str = 'end'
                         ) -> Tuple[Optional[datetime.datetime],
                                    Optional[datetime.datetime]]:
    start = forms.get(start_name, None)
    end = forms.get(end_name, None)
    start_date = None
    end_date = None
    try:
        print('=====')
        print(start, end)
        print('=====')
        if start:
            start_date = parse_iso(start)
        if end:
            end_date = parse_iso(end)
    except BaseException:
        abort(400, 'Fecha en formato equivocada')
    return start_date, end_date


def convert_to_cent(dec) -> int:
    if not isinstance(dec, Decimal):
        dec = Decimal(dec)
    return int(dec * 100)


def parse_start_end_date_with_default(
        form: Mapping[str, str],
        start: datetime.date, end: datetime.date) -> Tuple[datetime.date, datetime.date]:
    new_start, new_end = parse_start_end_date(form)
    new_end_res = end if new_end is None else new_end.date()
    new_start_res = start if new_start is None else new_start.date()
    return new_start_res, new_end_res
