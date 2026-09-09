from odoo import api, fields, models


class PayrollHoliday(models.Model):
    _name = 'payroll.holiday'
    _description = 'Feriado / Día de descanso obligatorio'
    _order = 'date desc'

    name = fields.Char(string='Descripción', required=True)
    date = fields.Date(string='Fecha', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa',
        help='Vacío = aplica a todas las empresas.')

    _sql_constraints = [
        ('uniq_date_company', 'unique(date, company_id)',
         'Ya existe un feriado con esa fecha para esa empresa.'),
    ]

    @api.depends('name', 'date')
    def _compute_display_name(self):
        for holiday in self:
            holiday.display_name = ' - '.join(filter(None, [
                fields.Date.to_string(holiday.date), holiday.name]))

    @api.model
    def is_holiday(self, date, company):
        """True si `date` es feriado para `company` (o feriado global)."""
        return bool(self.sudo().search_count([
            ('date', '=', date),
            ('company_id', 'in', [company.id, False]),
        ]))
