from decimal import Decimal
from typing import Optional, Dict, cast, List
import zeep
import barcode
import datetime
import requests
import time

from henry.xades import xades
from henry.base.dbapi import DBApiGeneric
from henry.base.common import HenryException
from henry.base.serialization import json_dumps
from henry.invoice.dao import SRINota, SRINotaStatus, Invoice, CommResult
from henry.product.dao import Store
from henry import constants
from henry.common import strip_accents, aes_encrypt

REMAP_SRI_STATUS = {
    SRINotaStatus.CREATED: 'NO ENVIADO',
    SRINotaStatus.CREATED_SENT: 'VALIDADO',
    SRINotaStatus.CREATED_SENT_VALIDATED: 'AUTORIZADO',
}

def extract_auth_status(ans):
    if (ans is not None
            and hasattr(ans, 'autorizaciones')
            and hasattr(ans.autorizaciones, 'autorizacion')
            and ans.autorizaciones.autorizacion
            and 'estado' in ans.autorizaciones.autorizacion[0]):
        return ans.autorizaciones.autorizacion[0].estado
    return None


class WsEnvironment:
    name: str
    code: str
    validate_url: str
    authorize_url: str

    def __init__(self, name, code, validate_url, authorize_url):
        self.name = name
        self.code = code
        self.validate_url = validate_url
        self.authorize_url = authorize_url

        self._val_client = None
        self._auth_client = None

    def validate(self, xml_bytes):
        if self._val_client is None:
            self._val_client = zeep.Client(self.validate_url)
        return self._val_client.service.validarComprobante(xml_bytes)

    def authorize(self, access_code):
        if self._auth_client is None:
            self._auth_client = zeep.Client(self.authorize_url)
        ans = self._auth_client.service.autorizacionComprobante(access_code)
        text = str(ans)
        is_auth = False
        status_text = extract_auth_status(ans)
        if status_text == 'AUTORIZADO':
            status = SRINotaStatus.CREATED_SENT_VALIDATED
        elif status_text == 'EN PROCESO':
            status = SRINotaStatus.CREATED_SENT
        else:
            status = SRINotaStatus.VALIDATED_FAILED
        return status, text


ID_TO_CERT_PATH = {
    1: {
        'key': constants.P12_KEY_QUINAL,
        'path': constants.P12_FILENAME_QUINAL,
    },
    3: {
        'key': constants.P12_KEY_CORP,
        'path': constants.P12_FILENAME_CORP,
    },
}


def compute_access_code(inv: Invoice, ws: WsEnvironment):
    timestamp = inv.meta.timestamp
    assert timestamp is not None
    fecha = '{:02}{:02}{:04}'.format(
        timestamp.day, timestamp.month, timestamp.year)
    tipo_comp = '01'  # 01 = factura
    assert inv.meta.almacen_ruc is not None
    ruc = inv.meta.almacen_ruc
    numero = '{:09}'.format(int(inv.meta.codigo or 0))  # num de factura
    codigo_numero = '12345678'  # puede ser lo q sea de 8 digitos
    tipo_emision = '1'
    serie = '001001'
    ambiente = ws.code  # 1 = prueba 2 = prod

    access_key_48 = ''.join(
        [fecha, tipo_comp, ruc, ambiente, serie, numero, codigo_numero, tipo_emision])

    access_key = access_key_48 + str(xades.generate_checkcode(access_key_48))
    return access_key


class IdType:
    RUC = '04'
    CEDULA = '05'
    CONS_FINAL = '07'


def guess_id_type(client_id):
    if len(client_id) == 10:
        return IdType.CEDULA
    if len(client_id) > 10:
        return IdType.RUC
    return IdType.CONS_FINAL


def inv_to_sri_dict(inv: Invoice, sri_nota: SRINota,
                    dbapi: DBApiGeneric, ws: WsEnvironment) -> Optional[Dict]:
    """Return the dict used to render xml."""
    assert inv.meta
    assert inv.meta.client
    assert inv.meta.timestamp is not None
    if inv.meta.almacen_id is None:
        return None
    store = dbapi.get(inv.meta.almacen_id, Store)
    if store is None:
        return None
    tipo_ident = guess_id_type(inv.meta.client.codigo)
    # 99 para consumidor final
    ts = inv.meta.timestamp
    access = sri_nota.access_code
    if access is None:
        access = compute_access_code(inv, ws)
    if tipo_ident == IdType.CONS_FINAL:
        comprador = 'CONSUMIDOR FINAL'
        id_compra = '9999999999999'
    else:
        assert inv.meta.client.fullname is not None
        comprador = inv.meta.client.fullname
        assert inv.meta.client.codigo is not None
        id_compra = inv.meta.client.codigo
    assert inv.meta.codigo is not None
    assert store is not None
    res = {
        'ambiente': ws.code,
        'razon_social': store.nombre,
        'ruc': store.ruc,
        'clave_acceso': access,
        'codigo': '{:09}'.format(int(inv.meta.codigo)),
        'dir_matriz': store.address,
        'fecha': '{:02}/{:02}/{:04}'.format(ts.day, ts.month, ts.year),
        'tipo_identificacion_comprador': tipo_ident,
        'id_comprador': id_compra,
        'razon_social_comprador': comprador,
        'subtotal': (Decimal(inv.meta.subtotal or 0) - Decimal(inv.meta.discount or 0)) / 100,
        'iva': Decimal(inv.meta.tax or 0) / 100,
        'descuento': Decimal(inv.meta.discount or 0) / 100,
        'total': Decimal(inv.meta.total or 0) / 100,
        'tax_percent': inv.meta.tax_percent,
        'detalles': []
    }
    for item in inv.items:
        assert item.prod is not None
        assert item.prod.precio1 is not None
        assert item.prod.precio2 is not None
        assert item.cant is not None
        assert item.prod.cant_mayorista is not None
        if item.cant >= item.prod.cant_mayorista:
            desc = (item.prod.precio1 - item.prod.precio2) * item.cant
        else:
            desc = Decimal(0)
        total_sin_impuesto = item.prod.precio1 * item.cant - desc
        if inv.meta.discount_percent > 0:
            additional_desc = total_sin_impuesto * inv.meta.discount_percent / 100
            total_sin_impuesto -= additional_desc
            desc += additional_desc
        total_impuesto = inv.meta.tax_percent * total_sin_impuesto / 100
        item_dict = {
            'id': item.prod.prod_id,
            'nombre': item.prod.nombre,
            'cantidad': item.cant,
            'precio': Decimal(item.prod.precio1) / 100,
            'descuento': Decimal(desc) / 100,
            'total_sin_impuesto': Decimal(total_sin_impuesto) / 100,
            'total_impuesto': Decimal(total_impuesto) / 100
        }
        cast(List, res['detalles']).append(item_dict)
    return res


def generate_xml_paths(sri_nota: SRINota,
                       file_manager, jinja_env, dbapi, ws):
    inv = sri_nota.load_nota(file_manager)
    if inv is None:
        raise HenryException(
            'Inv corresponding a {} not found'.format(sri_nota.uid))

    xml_dict = inv_to_sri_dict(inv, sri_nota, dbapi, ws)
    if xml_dict is None:
        return None, None
    xml_text = jinja_env.get_template(
        'invoice/factura_2_0_template.xml').render(xml_dict)
    xml_inv_location = '{}/{}.xml'.format(sri_nota.orig_timestamp.isoformat(),
                                          sri_nota.access_code)
    file_manager.put_file(xml_inv_location, xml_text)
    sri_nota.xml_inv_location = xml_inv_location
    assert sri_nota.almacen_id
    keyinfo = ID_TO_CERT_PATH.get(sri_nota.almacen_id)
    if keyinfo is None:
        raise HenryException('Wrong almacen_id {}'.format(sri_nota.almacen_id))
    p12filename = keyinfo['path']
    p12key = keyinfo['key']
    print(p12filename, p12key)

    xml_inv_signed_location = '{}-signed.xml'.format(sri_nota.access_code)
    signed_xml = xades.sign_xml(xml_text, p12filename, p12key).decode('utf-8')
    file_manager.put_file(xml_inv_signed_location, signed_xml)

    dbapi.update(sri_nota, {
        'xml_inv_location': xml_inv_location,
        'xml_inv_signed_location': xml_inv_signed_location,
    })
    return sri_nota.xml_inv_location, sri_nota.xml_inv_signed_location


def get_or_generate_xml_paths(
        sri_nota: SRINota,
        file_manager,
        jinja_env,
        dbapi,
        ws):
    if not sri_nota.xml_inv_location or not sri_nota.xml_inv_signed_location:
        return generate_xml_paths(sri_nota, file_manager, jinja_env, dbapi, ws)
    return sri_nota.xml_inv_location, sri_nota.xml_inv_signed_location


def sri_nota_from_nota(inv: Invoice, ws: WsEnvironment):
    sri_nota = SRINota()
    sri_nota.uid = inv.meta.uid
    sri_nota.almacen_id = inv.meta.almacen_id
    sri_nota.almacen_ruc = inv.meta.almacen_ruc
    sri_nota.orig_codigo = inv.meta.codigo
    sri_nota.orig_timestamp = inv.meta.timestamp
    sri_nota.timestamp_received = datetime.datetime.now()
    sri_nota.status = SRINotaStatus.CREATED
    sri_nota.total = Decimal(inv.meta.total) / 100
    sri_nota.tax = Decimal(inv.meta.tax) / 100
    sri_nota.discount = Decimal(inv.meta.discount) / 100
    if inv.meta.client:
        sri_nota.buyer_ruc = inv.meta.client.codigo
        sri_nota.buyer_name = inv.meta.client.fullname
    sri_nota.json_inv_location = inv.filepath_format
    sri_nota.xml_inv_location = ''
    sri_nota.xml_inv_signed_location = ''
    sri_nota.all_comm_path = ''
    if ws is not None:
        sri_nota.access_code = compute_access_code(inv, ws)
    return sri_nota


def sri_nota_to_extra(
        sri_nota: SRINota,
        store: Store,
        ws: WsEnvironment):
    bcode = barcode.Gs1_128(sri_nota.access_code)
    svg_code = bcode.render().decode('utf-8')
    index = svg_code.find('<svg')
    svg_code = svg_code[index:]
    extra = {
        'ambiente': ws.name,
        'name': store.nombre,
        'address': store.address,
        'access_code': sri_nota.access_code,
        'ruc': sri_nota.almacen_ruc,
        'svg_code': svg_code,
        'status': REMAP_SRI_STATUS.get(sri_nota.status or '', 'NO ENVIADO')
    }
    return extra


def send_remote(nota, create, is_prod):
    content = {
        'action': 'create' if create else 'delete',
        'inv': nota,
        'uid': nota.meta.uid,
        'is_prod': is_prod
    }
    msg_bytes = json_dumps(content).encode('utf-8')
    encrypted = aes_encrypt(msg_bytes)

    resp = requests.post(constants.REMOTE_ADDR, data=encrypted)
    return resp.status_code == 200, resp.text


def send_sri_nota(sri_nota, ws, file_manager, jinja_env, dbapi):
    if sri_nota.almacen_id not in (1, 3):
        return False

    relpath, signed_path = get_or_generate_xml_paths(
        sri_nota, file_manager, jinja_env, dbapi, ws)

    if sri_nota.status == SRINotaStatus.CREATED:
        fullpath = file_manager.make_fullpath(signed_path)
        with open(fullpath, 'rb') as f:
            xml_content = f.read()
        try:
            ans = ws.validate(xml_content)
        except Exception as e:
            message = str(e)
            result = CommResult(
                status='failed',
                request_type='ENVIAR',
                request_sent=xml_content.decode('utf-8'),
                response=message,
                environment=ws.name == 'PRODUCCION',
                timestamp=datetime.datetime.now(),
            )
            sri_nota.append_comm_result(result, file_manager, dbapi)
            dbapi.update(sri_nota, {
                'status': SRINotaStatus.VALIDATED_FAILED
            })
            return False

        result = CommResult(
            status='success',
            request_type='ENVIAR',
            request_sent=xml_content.decode('utf-8'),
            response=str(ans),
            environment=ws.name == 'PRODUCCION',
            timestamp=datetime.datetime.now(),
        )
        sri_nota.append_comm_result(result, file_manager, dbapi)
        dbapi.update(sri_nota, {
            'status': SRINotaStatus.CREATED_SENT
        })
        return True


def auth_sri_nota(sri_nota, ws, dbapi, file_manager):
    try:
        status, text = ws.authorize(sri_nota.access_code)
    except Exception as e:
        message = str(e)
        result = CommResult(
            status='failed',
            request_type='AUTORIZAR',
            request_sent=sri_nota.access_code,
            response=message,
            environment=ws.name == 'PRODUCCION',
            timestamp=datetime.datetime.now(),
        )
        sri_nota.append_comm_result(result, file_manager, dbapi)
        dbapi.update(sri_nota, {
            'status': SRINotaStatus.VALIDATED_FAILED
        })
        return False

    result = CommResult(
        status=status,
        request_type='AUTORIZAR',
        request_sent=sri_nota.access_code,
        response=text,
        environment=ws.name == 'PRODUCCION',
        timestamp=datetime.datetime.now(),
    )
    sri_nota.append_comm_result(result, file_manager, dbapi)
    dbapi.update(sri_nota, {
        'status': status,
    })
    return True


def send_sri_by_date_range(start, end, dbapi, file_manager, alm_id_to_ws, jinja_env):
    sri_notas = dbapi.search(
            SRINota, **{'timestamp_received-lte': end,
                        'timestamp_received-gte': start,
                        'almacen_id-ne': 2,
                        'status': SRINotaStatus.CREATED})
    for sri_nota in sri_notas:
        ws = alm_id_to_ws(sri_nota.almacen_id)
        if not ws:
            continue
        print('send', sri_nota.uid)
        try:
            send_sri_nota(
                sri_nota,
                ws=ws,
                dbapi=dbapi,
                file_manager=file_manager,
                jinja_env=jinja_env)
        except HenryException as h:
            print(h)
            import traceback
            traceback.print_exc()
            print('failed')
        else:
            print('done send', sri_nota.uid)

    time.sleep(1)
    sri_notas = dbapi.search(
            SRINota, **{'timestamp_received-lte': end,
                        'timestamp_received-gte': start,
                        'almacen_id-ne': 2,
                        'status': SRINotaStatus.CREATED_SENT})
    for sri_nota in sri_notas:
        ws = alm_id_to_ws(sri_nota.almacen_id)
        if not ws:
            continue
        print('auth', sri_nota.uid)
        auth_sri_nota(sri_nota,
            ws=ws,
            dbapi=dbapi,
            file_manager=file_manager)
        print('done auth', sri_nota.uid)

