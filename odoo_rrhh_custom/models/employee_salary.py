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
        help='Salario en USD convertido a Lempiras con la tasa de cambio vigente '
             '(tabla de tasas de res.currency) a la fecha efectiva del salario.')
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

    def _get_conversion_context(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        date = self.effective_date or fields.Date.context_today(self)
        return company, date

    @api.depends('base_salary', 'effective_date', 'company_id')
    def _compute_base_salary_lps(self):
        usd = self.env.ref('base.USD')
        for salary in self:
            company, date = salary._get_conversion_context()
            if not salary.base_salary or not company.currency_id:
                salary.base_salary_lps = 0.0
                continue
            salary.base_salary_lps = usd._convert(
                salary.base_salary, company.currency_id, company, date)

    @api.depends('base_salary_lps', 'bonus')
    def _compute_net_salary_lps(self):
        for salary in self:
            salary.net_salary_lps = salary.base_salary_lps + salary.bonus

    @api.depends('net_salary_lps', 'effective_date', 'company_id')
    def _compute_net_salary_usd(self):
        usd = self.env.ref('base.USD')
        for salary in self:
            company, date = salary._get_conversion_context()
            if not salary.net_salary_lps or not company.currency_id:
                salary.net_salary_usd = 0.0
                continue
            salary.net_salary_usd = company.currency_id._convert(
                salary.net_salary_lps, usd, company, date)

    @api.depends('net_salary_usd', 'effective_date')
    def _compute_display_name(self):
        for salary in self:
            if not salary.net_salary_usd:
                salary.display_name = _('Nuevo salario')
                continue
            date_label = format_date(self.env, salary.effective_date) if salary.effective_date else None
            amount = f'${salary.net_salary_usd:,.2f}'
            salary.display_name = f'{amount} ({date_label})' if date_label else amount
