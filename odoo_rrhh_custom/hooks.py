import csv
import os

_HISTORY_CSV = os.path.join(os.path.dirname(__file__), 'data', 'exchange_rate_history.csv')


def _load_exchange_rate_history(env):
    """Carga masiva (INSERT ... ON CONFLICT DO NOTHING) del histórico de tipo
    de cambio USD/Lempira del Banco Central de Honduras. Se hace por SQL
    directo, no por el ORM, porque son ~6700 filas y así el módulo se
    instala/actualiza en segundos en vez de minutos; es seguro repetir esta
    carga en cada actualización gracias al unique(date) del modelo."""
    if not os.path.exists(_HISTORY_CSV):
        return
    with open(_HISTORY_CSV, newline='', encoding='utf-8') as f:
        rows = [(row['date'], float(row['buy_rate']), float(row['sell_rate']))
                for row in csv.DictReader(f)]
    if not rows:
        return
    env.cr.executemany(
        """
        INSERT INTO hr_exchange_rate_history (date, buy_rate, sell_rate, create_date, write_date)
        VALUES (%s, %s, %s, now(), now())
        ON CONFLICT (date) DO NOTHING
        """,
        rows,
    )


def _update_hnl_current_rate(env):
    """Actualiza la tasa 'manual' genérica de Odoo (Ajustes > Monedas) para
    Lempiras con el último valor (Compra) del histórico recién cargado, en
    vez de dejar el dato de fábrica de 2010. Solo la usan cálculos fuera de
    Planilla (ej. 'Salario neto USD' en la ficha del empleado); Planilla
    resuelve su propia tasa por periodo desde hr.exchange.rate.history."""
    hnl = env['res.currency'].search([('name', '=', 'HNL')], limit=1)
    latest = env['hr.exchange.rate.history'].search([], order='date desc', limit=1)
    if not hnl or not latest:
        return
    for company in env['res.company'].search([]):
        env['res.currency.rate'].sudo().search([
            ('currency_id', '=', hnl.id),
            ('name', '=', latest.date),
            ('company_id', '=', company.id),
        ], limit=1).unlink()
        env['res.currency.rate'].sudo().create({
            'currency_id': hnl.id,
            'name': latest.date,
            'rate': latest.buy_rate,
            'company_id': company.id,
        })


def post_init_hook(env):
    _load_exchange_rate_history(env)
    _update_hnl_current_rate(env)
