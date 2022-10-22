import json
from decimal import Decimal
from typing import Optional, Dict, cast, List
import zeep
import barcode

from henry.xades import xades
from henry.base.dbapi import DBApiGeneric
from henry.base.common import HenryException
from henry.invoice.dao import Invoice, SRINota, SRINotaStatus
from henry.product.dao import Store
from henry import constants

REMAP_SRI_STATUS = {
    SRINotaStatus.CREATED: 'NO ENVIADO',
    SRINotaStatus.CREATED_SENT: 'VALIDADO',
    SRINotaStatus.CREATED_SENT_VALIDATED: 'AUTORIZADO',
}


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
        if (ans is not None
                and ans.autorizaciones.autorizacion
                and 'estado' in ans.autorizaciones.autorizacion[0]):
            is_auth = (
                ans.autorizaciones.autorizacion[0]['estado'] == 'AUTORIZADO')
        status = SRINotaStatus.CREATED_SENT_VALIDATED if is_auth else SRINotaStatus.VALIDATED_FAILED
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
        'subtotal': Decimal(inv.meta.subtotal or 0) / 100,
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
        if item.cant > item.prod.cant_mayorista:
            desc = (item.prod.precio1 - item.prod.precio2) * item.cant
        else:
            desc = Decimal(0)
        total_sin_impuesto = item.prod.precio1 * item.cant - desc
        total_impuesto = Decimal('0.12') * total_sin_impuesto
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


def sri_nota_to_nota_and_extra(
        sri_nota: SRINota,
        store: Store,
        file_manager,
        ws: WsEnvironment):
    json_env = json.loads(
        file_manager.get_file(sri_nota.json_inv_location))
    doc = Invoice.deserialize(json_env)
    if not doc:
        raise HenryException('Documento con codigo {} no existe'.format(
            sri_nota.uid))

    bcode = barcode.Gs1_128(sri_nota.access_code)
    svg_code = bcode.render().decode('utf-8')
    index = svg_code.find('<svg')
    svg_code = svg_code[index:]
    if doc.meta.client.codigo == 'NA':
        doc.meta.client.codigo = '9999999999999'

    extra = {
        'ambiente': ws.name,
        'name': store.nombre,
        'address': store.address,
        'access_code': sri_nota.access_code,
        'ruc': sri_nota.almacen_ruc,
        'svg_code': svg_code,
        'status': REMAP_SRI_STATUS.get(sri_nota.status or '', 'NO ENVIADO')
    }
    return doc, extra
