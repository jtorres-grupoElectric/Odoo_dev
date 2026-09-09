from odoo import api, fields, models


class ExchangeRateHistory(models.Model):
    _name = 'hr.exchange.rate.history'
    _description = 'Histórico de tipo de cambio USD/Lempira (Banco Central de Honduras)'
    _rec_name = 'date'
    _order = 'date desc'

    date = fields.Date(string='Fecha', required=True)
    buy_rate = fields.Float(string='Compra', required=True, digits=(12, 4))
    sell_rate = fields.Float(string='Venta', required=True, digits=(12, 4))

    _sql_constraints = [
        ('date_unique', 'unique(date)', 'Ya existe una tasa de cambio cargada para esa fecha.'),
    ]

    def get_buy_rate_on_or_before(self, target_date):
        """Tasa de compra vigente en target_date, o la del último día hábil
        anterior con dato publicado si esa fecha no tiene (fin de semana o
        feriado) — el Banco Central de Honduras solo publica en días hábiles."""
        record = self.search([('date', '<=', target_date)], order='date desc', limit=1)
        return (record.date, record.buy_rate) if record else (False, 0.0)

    @api.model
    def _parse_date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(str(value)[:10])
        except ValueError:
            return False

    @api.model
    def _safe_float(self, value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def sync_from_bch(self, config, reciente=30):
        """Trae Compra y Venta recientes de la API del BCH y las guarda aquí
        mismo (upsert por fecha) — mismo modelo que ya usa Planilla para
        resolver la tasa, sin tabla paralela. `reciente` es la cantidad de
        cifras más recientes a pedir por indicador; con el cron diario 30
        alcanza de sobra para no dejar huecos si el BCH tarda en publicar."""
        from .exchange_rate_config import BCH_INDICATOR_BUY, BCH_INDICATOR_SELL

        buys = {self._parse_date(item.get('Fecha')): self._safe_float(item.get('Valor'))
                for item in config._api_get(BCH_INDICATOR_BUY, reciente=reciente)}
        sells = {self._parse_date(item.get('Fecha')): self._safe_float(item.get('Valor'))
                 for item in config._api_get(BCH_INDICATOR_SELL, reciente=reciente)}
        buys.pop(False, None)
        sells.pop(False, None)

        processed = 0
        for rate_date in sorted(set(buys) & set(sells)):
            buy_value, sell_value = buys[rate_date], sells[rate_date]
            if buy_value <= 0 or sell_value <= 0:
                continue
            record = self.search([('date', '=', rate_date)], limit=1)
            if record:
                record.write({'buy_rate': buy_value, 'sell_rate': sell_value})
            else:
                self.create({'date': rate_date, 'buy_rate': buy_value, 'sell_rate': sell_value})
            processed += 1
        return processed
