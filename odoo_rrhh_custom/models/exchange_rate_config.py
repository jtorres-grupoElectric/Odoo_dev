import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Indicadores del Banco Central de Honduras (API oficial, bchapi-am.azure-api.net):
# 619 = tipo de cambio Compra, 620 = Venta. Confirmados con el cliente — no
# configurables porque son fijos del lado del BCH, no de nuestra instalación.
BCH_INDICATOR_BUY = 619
BCH_INDICATOR_SELL = 620


class ExchangeRateConfig(models.Model):
    _name = 'hr.exchange.rate.config'
    _description = 'Configuración de sincronización del tipo de cambio (Banco Central de Honduras)'

    name = fields.Char(default='Banco Central de Honduras', required=True)
    active = fields.Boolean(default=True, help='Si está desactivado, el cron diario no sincroniza.')
    api_key = fields.Char(
        string='Clave API BCH', groups='base.group_system',
        help='Clave de la suscripción a la API del Banco Central (bchapi-am.azure-api.net). '
             'Solo visible para Administración del sistema.')
    base_url = fields.Char(
        string='URL base', required=True,
        default='https://bchapi-am.azure-api.net/api/v1')
    last_sync = fields.Datetime(string='Última sincronización', readonly=True)
    last_status = fields.Text(string='Último resultado', readonly=True)

    def _get_singleton(self):
        rec = self.search([], limit=1)
        if not rec:
            rec = self.create({})
        return rec

    def _api_get(self, indicator_id, reciente=30):
        self.ensure_one()
        if not self.api_key:
            raise UserError(_('Debes configurar la Clave API BCH antes de sincronizar.'))

        base = (self.base_url or '').rstrip('/')
        params = urlencode({'formato': 'Json', 'reciente': reciente})
        url = f'{base}/indicadores/{indicator_id}/cifras?{params}'
        req = Request(url, headers={'Cache-Control': 'no-cache', 'clave': self.api_key}, method='GET')

        try:
            with urlopen(req, timeout=25) as response:
                raw = response.read().decode('utf-8')
        except HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            raise UserError(_('Error HTTP del BCH %s: %s') % (e.code, body[:500]))
        except URLError as e:
            raise UserError(_('No se pudo conectar con el BCH: %s') % e)

        try:
            data = json.loads(raw)
        except ValueError:
            raise UserError(_('La respuesta del BCH no es JSON válido: %s') % raw[:500])
        if not isinstance(data, list):
            raise UserError(_('Respuesta del BCH inesperada: %s') % str(data)[:500])
        return data

    def action_test_connection(self):
        self.ensure_one()
        data = self._api_get(BCH_INDICATOR_BUY, reciente=1)
        if not data:
            raise UserError(_('Conexión correcta, pero el BCH no devolvió registros.'))
        first = data[0]
        self.write({'last_status': _('Conexión correcta. Último dato de compra: %s = %s') % (
            str(first.get('Fecha', ''))[:10], first.get('Valor'))})
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('BCH conectado'), 'message': self.last_status,
                       'type': 'success', 'sticky': False},
        }

    def action_sync_now(self):
        self.ensure_one()
        count = self.env['hr.exchange.rate.history'].sudo().sync_from_bch(self)
        self.write({
            'last_sync': fields.Datetime.now(),
            'last_status': _('Sincronización correcta. Tasas actualizadas: %s') % count,
        })
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Tipo de cambio actualizado'), 'message': self.last_status,
                       'type': 'success', 'sticky': False},
        }

    @api.model
    def cron_sync_bch_rates(self):
        config = self._get_singleton()
        if not config.active or not config.api_key:
            return False
        try:
            count = self.env['hr.exchange.rate.history'].sudo().sync_from_bch(config)
            config.write({
                'last_sync': fields.Datetime.now(),
                'last_status': _('Cron ejecutado correctamente. Tasas actualizadas: %s') % count,
            })
        except Exception as e:
            config.write({'last_status': str(e)})
        return True
