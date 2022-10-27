import datetime
import os
from decimal import Decimal
from jinja2 import Environment, FileSystemLoader
from henry.invoice.dao import PaymentFormat
from henry.misc import id_type, fix_id, abs_string, value_from_cents, get_total
from henry.common import strip_accents


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

def shorten_to(line, max_line_size):
    if len(line) <= max_line_size:
        return line
    tokens = line.split()
    new_toks = [t[:5] for t in tokens]
    new_line = ' '.join(new_toks)
    if len(new_line) > max_line_size:
        new_line = new_line[:max_line_size]
    return new_line


def left_right_just(first, second, max_line_size):
    spaces = max_line_size - len(first) - len(second)
    return '{}{}{}'.format(first, ' ' * spaces, second)


def format_invoice_line(row, max_line_size):
    # make sure product is within max_line_size
    desc = shorten_to(row.prod.nombre, max_line_size)
    desc = strip_accents(desc)
    p = value_from_cents(row.prod.precio1)
    first_elem = '{} x {:.2f}'.format(row.cant, p)
    second_elem = '{:.2f}'.format(row.cant * p)
    return '{}\n{}'.format(
            desc, left_right_just(first_elem, second_elem, max_line_size))

def left_right_number(first, second, max_line_size):
    num = value_from_cents(second)
    second_str = '{:.2f}'.format(num)
    return left_right_just(first, second_str, max_line_size)


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
        'format_invoice_line': format_invoice_line,
        'left_right_just': left_right_just,
        'left_right_number': left_right_number,
        'strip_accents': strip_accents,
    })
    return jinja_env
