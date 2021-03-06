import datetime
import os
from decimal import Decimal
from jinja2 import Environment, FileSystemLoader
from henry.invoice.dao import PaymentFormat
from henry.misc import id_type, fix_id, abs_string, value_from_cents, get_total


def my_finalize(x):
    return '' if x is None else x


def fix_path(x):
    return os.path.split(x)[1]


def display_date(x):
    if isinstance(x, datetime.datetime):
        return x.date().isoformat()
    return x.isoformat()


def decimal_places(dec, places='0.01'):
    return dec.quantize(Decimal(places))

def normalize_decimal(dec):
    return ('%f' % dec).rstrip('0').rstrip('.')

def make_jinja_env(template_paths):
    jinja_env = Environment(loader=FileSystemLoader(template_paths),
                            finalize=my_finalize)
    jinja_env.globals.update({
        'id_type': id_type,
        'fix_id': fix_id,
        'abs': abs_string,
        'value_from_cents': value_from_cents,
        'get_total': get_total,
        'today': datetime.date.today,
        'PaymentFormat': PaymentFormat,
        'fix_path': fix_path,
        'display_date': display_date,
        'decimal_places': decimal_places,
        'normalize_decimal': normalize_decimal,
    })
    return jinja_env
