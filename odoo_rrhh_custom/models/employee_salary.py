from odoo import _, api, fields, models
from odoo.tools import format_date


class EmployeeSalary(models.Model):
    _name = 'employee.salary'
    _description = 'Salario Individual'
    _order = 'effective_date desc, id desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    base_salary = fields.Float(string='Salario en USD', required=True)
    base_salary_lps = fields.Float(
        string='Salario LPS', compute='_compute_base_salary_lps',
        help='Salario en USD convertido a Lempiras con la tasa de compra del Banco '
             'Central de Honduras (hr.exchange.rate.history) vigente a la fecha '
             'efectiva del salario — la misma fuente que usa Planilla.')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    effective_date = fields.Date(string='Fecha efectiva', required=True, default=fields.Date.context_today)
    end_date = fields.Date(string='Fecha de finalización')
    is_active = fields.Boolean(string='Activo', default=True)
    pays_in_usd = fields.Boolean(
        string='Pago en cuenta de dólares', default=False,
        help='El neto a pagar se deposita directamente en cuenta en USD, convertido '
             'con la tasa de cambio de la planilla del periodo, en vez de pagarse en Lempiras.')
    bonus = fields.Float(
        string='Bono LPS',
        help='Bonificación en Lempiras, aplicada sobre el salario ya convertido (Salario LPS).')
    net_salary_lps = fields.Float(
        string='Salario neto LPS', compute='_compute_net_salary_lps', store=True)
    net_salary_usd = fields.Float(
        string='Salario neto USD', compute='_compute_net_salary_usd', store=True)
    notes = fields.Text(string='Notas')

    def _get_conversion_date(self):
        self.ensure_one()
        return self.effective_date or fields.Date.context_today(self)

    def _get_usd_buy_rate(self):
        """Tasa de compra USD→Lempira del Banco Central vigente a la fecha
        efectiva del salario. Misma fuente que usa Planilla
        (hr.exchange.rate.history), no la tabla genérica de Odoo
        (res.currency.rate), que nadie mantiene actualizada."""
        self.ensure_one()
        History = self.env['hr.exchange.rate.history'].sudo()
        _resolved_date, rate = History.get_buy_rate_on_or_before(self._get_conversion_date())
        return rate

    @api.depends('base_salary', 'effective_date')
    def _compute_base_salary_lps(self):
        for salary in self:
            rate = salary._get_usd_buy_rate()
            salary.base_salary_lps = (salary.base_salary or 0.0) * rate

    @api.depends('base_salary_lps', 'bonus')
    def _compute_net_salary_lps(self):
        for salary in self:
            salary.net_salary_lps = salary.base_salary_lps + salary.bonus

    @api.depends('net_salary_lps', 'effective_date')
    def _compute_net_salary_usd(self):
        for salary in self:
            rate = salary._get_usd_buy_rate()
            salary.net_salary_usd = (salary.net_salary_lps / rate) if rate else 0.0

    @api.depends('net_salary_usd', 'effective_date')
    def _compute_display_name(self):
        for salary in self:
            if not salary.net_salary_usd:
                salary.display_name = _('Nuevo salario')
                continue
            date_label = format_date(self.env, salary.effective_date) if salary.effective_date else None
            amount = f'${salary.net_salary_usd:,.2f}'
            salary.display_name = f'{amount} ({date_label})' if date_label else amount
