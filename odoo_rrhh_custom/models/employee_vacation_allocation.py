from odoo import api, fields, models

# Código del Trabajo de Honduras, Artículo 346: días de vacaciones remuneradas
# según años de servicio continuo cumplidos con el mismo empleador.
HONDURAS_VACATION_DAYS_BY_YEARS = {
    1: 10,
    2: 12,
    3: 15,
}
HONDURAS_VACATION_DAYS_4_PLUS = 20


class EmployeeVacationAllocation(models.Model):
    _name = 'employee.vacation.allocation'
    _description = 'Saldo de Vacaciones'
    _rec_name = 'employee_id'
    _order = 'year desc, id desc'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    year = fields.Integer(
        string='Año', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    years_of_service = fields.Integer(
        string='Años de servicio', compute='_compute_years_of_service')
    allocated_days = fields.Float(string='Días asignados', required=True)
    used_days = fields.Float(string='Días usados', compute='_compute_used_days')
    available_days = fields.Float(string='Días disponibles', compute='_compute_used_days')
    notes = fields.Text(string='Notas')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for allocation in self:
            if allocation.employee_id.company_id:
                allocation.company_id = allocation.employee_id.company_id

    @api.onchange('employee_id', 'year')
    def _onchange_calculate_legal_days(self):
        for allocation in self:
            if allocation.employee_id.rrhh_hire_date:
                allocation.allocated_days = allocation._get_honduras_legal_days()

    def action_calculate_legal_days(self):
        for allocation in self:
            allocation.allocated_days = allocation._get_honduras_legal_days()

    def _get_or_create_current_year(self, employee):
        """Devuelve el saldo del año actual del empleado, creándolo si no existe
        todavía — el saldo se calcula solo por antigüedad, sin que nadie tenga
        que darlo de alta ni pulsar el botón de cálculo a mano."""
        year = fields.Date.context_today(self).year
        allocation = self.search([
            ('employee_id', '=', employee.id),
            ('year', '=', year),
        ], limit=1)
        if not allocation:
            allocation = self.create({
                'employee_id': employee.id,
                'company_id': employee.company_id.id,
                'year': year,
                'allocated_days': 0.0,
            })
            allocation.allocated_days = allocation._get_honduras_legal_days()
        return allocation

    def _get_honduras_legal_days(self):
        self.ensure_one()
        hire_date = self.employee_id.rrhh_hire_date
        if not hire_date or not self.year:
            return 0.0
        years_completed = self.year - hire_date.year
        if years_completed >= 4:
            return HONDURAS_VACATION_DAYS_4_PLUS
        return HONDURAS_VACATION_DAYS_BY_YEARS.get(years_completed, 0)

    @api.depends('employee_id.rrhh_hire_date', 'year')
    def _compute_years_of_service(self):
        for allocation in self:
            hire_date = allocation.employee_id.rrhh_hire_date
            allocation.years_of_service = (allocation.year - hire_date.year) if hire_date else 0

    _sql_constraints = [
        ('employee_year_company_unique', 'unique(employee_id, year, company_id)',
         'Ya existe una asignación de vacaciones para este empleado en ese año.'),
    ]

    @api.depends('employee_id', 'year', 'allocated_days')
    def _compute_used_days(self):
        for allocation in self:
            # El saldo es un cálculo interno del sistema, no una consulta directa
            # del usuario sobre permisos laborales de terceros: se usa sudo() para
            # que no dependa de que el usuario tenga acceso a labor.permission.
            permissions = self.env['labor.permission'].sudo().search([
                ('employee_id', '=', allocation.employee_id.id),
                ('permission_type', '=', 'vacacion'),
                ('state', '=', 'approved'),
                ('start_date', '>=', f'{allocation.year}-01-01'),
                ('start_date', '<=', f'{allocation.year}-12-31'),
            ])
            allocation.used_days = sum(permissions.mapped('days_count'))
            allocation.available_days = allocation.allocated_days - allocation.used_days
