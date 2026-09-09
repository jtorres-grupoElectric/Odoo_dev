from odoo import api, fields, models


class PayrollHolidayWorked(models.Model):
    _name = 'payroll.holiday.worked'
    _description = 'Feriado trabajado por un empleado'
    _order = 'date desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    date = fields.Date(string='Fecha', required=True)
    holiday_id = fields.Many2one('payroll.holiday', string='Feriado')
    source = fields.Selection([
        ('manual', 'Manual'),
        ('attendance_import', 'Reporte de asistencia'),
    ], string='Origen', default='manual', required=True)

    _sql_constraints = [
        ('uniq_employee_date', 'unique(employee_id, date)',
         'Ya existe un registro de feriado trabajado para ese empleado en esa fecha.'),
    ]

    @api.depends('employee_id.name', 'date')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ' - '.join(filter(None, [
                rec.employee_id.name, fields.Date.to_string(rec.date)]))
