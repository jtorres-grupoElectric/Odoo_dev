from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    rrhh_salary_ids = fields.One2many(
        'employee.salary', 'employee_id', string='Historial salarial')
    rrhh_current_salary_id = fields.Many2one(
        'employee.salary', string='Salario actual', compute='_compute_rrhh_current_salary')
    rrhh_overtime_ids = fields.One2many(
        'employee.overtime', 'employee_id', string='Horas extra')
    rrhh_vacation_allocation_ids = fields.One2many(
        'employee.vacation.allocation', 'employee_id', string='Asignaciones de vacaciones')
    rrhh_labor_permission_ids = fields.One2many(
        'labor.permission', 'employee_id', string='Permisos laborales')
    rrhh_holiday_worked_ids = fields.One2many(
        'payroll.holiday.worked', 'employee_id', string='Feriados trabajados')
    rrhh_document_request_ids = fields.One2many(
        'employee.document.request', 'employee_id', string='Solicitudes de documentos')
    rrhh_document_request_id = fields.Many2one(
        'employee.document.request', string='Solicitud de documentos vigente',
        compute='_compute_rrhh_document_request_id', store=True)
    rrhh_document_line_ids = fields.One2many(
        related='rrhh_document_request_id.document_line_ids', string='Documentos', readonly=False)
    rrhh_document_state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Parcial'),
        ('complete', 'Completo'),
        ('verified', 'Verificado'),
        ('none', 'Sin solicitud'),
    ], string='Estado de documentos', compute='_compute_rrhh_document_state')
    rrhh_vacation_available_days = fields.Float(
        string='Días de vacaciones disponibles', compute='_compute_rrhh_vacation_available_days')
    rrhh_overtime_count = fields.Integer(
        string='Cantidad de horas extra', compute='_compute_rrhh_overtime_count')
    rrhh_hire_date = fields.Date(string='Fecha de ingreso')
    # Datos de perfil sin equivalente estándar en hr.employee, volcados desde
    # hiring.candidate al finalizar la contratación.
    rrhh_rtn = fields.Char(string='RTN')
    rrhh_inss_no = fields.Char(string='No. INSS')
    rrhh_rap_no = fields.Char(string='No. RAP')
    rrhh_education_level = fields.Char(string='Nivel de estudios')
    rrhh_emergency_relationship = fields.Char(string='Parentesco (contacto de emergencia)')
    rrhh_bank_id = fields.Many2one('res.bank', string='Banco')
    rrhh_bank_account_number = fields.Char(string='No. de cuenta bancaria')

    @api.depends('rrhh_document_request_ids')
    def _compute_rrhh_document_request_id(self):
        # Cada perfil tiene su propia solicitud de documentos, sin excepción:
        # si el empleado no tiene una todavía (p. ej. no vino del flujo de
        # contratación, como los socios), se crea aquí vacía la primera vez
        # que se abre su ficha, igual que con el saldo de vacaciones — con
        # sudo() porque un Empleado normal no tiene permiso de creación
        # sobre employee.document.request (ver ir.model.access.csv).
        for employee in self:
            request = employee.rrhh_document_request_ids.sorted('request_date', reverse=True)[:1]
            if not request and isinstance(employee.id, int):
                request = self.env['employee.document.request'].sudo().create({
                    'employee_id': employee.id,
                    'company_id': employee.company_id.id,
                })
            employee.rrhh_document_request_id = request

    @api.depends('rrhh_document_request_id.state')
    def _compute_rrhh_document_state(self):
        for employee in self:
            employee.rrhh_document_state = employee.rrhh_document_request_id.state or 'none'

    @api.depends('rrhh_overtime_ids')
    def _compute_rrhh_overtime_count(self):
        for employee in self:
            employee.rrhh_overtime_count = len(employee.rrhh_overtime_ids)

    @api.depends('rrhh_salary_ids.is_active', 'rrhh_salary_ids.effective_date')
    def _compute_rrhh_current_salary(self):
        for employee in self:
            employee.rrhh_current_salary_id = employee.rrhh_salary_ids.filtered(
                'is_active'
            ).sorted('effective_date', reverse=True)[:1]

    @api.depends('rrhh_vacation_allocation_ids.available_days', 'rrhh_vacation_allocation_ids.year',
                 'rrhh_hire_date')
    def _compute_rrhh_vacation_available_days(self):
        # El saldo se calcula solo por antigüedad (sin botón): si el empleado
        # todavía no tiene una asignación para el año en curso, se crea aquí
        # con sudo(), igual que en labor_permission.action_approve_rrhh(),
        # porque un Empleado normal no tiene permiso de creación sobre
        # employee.vacation.allocation (ver ir.model.access.csv).
        Allocation = self.env['employee.vacation.allocation'].sudo()
        for employee in self:
            if not employee.rrhh_hire_date or not isinstance(employee.id, int):
                employee.rrhh_vacation_available_days = 0.0
                continue
            allocation = Allocation._get_or_create_current_year(employee)
            employee.rrhh_vacation_available_days = allocation.available_days if allocation else 0.0

    def action_view_rrhh_salaries(self):
        self.ensure_one()
        return {
            'name': 'Historial salarial',
            'type': 'ir.actions.act_window',
            'res_model': 'employee.salary',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_rrhh_overtime(self):
        self.ensure_one()
        return {
            'name': 'Horas extra',
            'type': 'ir.actions.act_window',
            'res_model': 'employee.overtime',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_rrhh_vacations(self):
        self.ensure_one()
        return {
            'name': 'Saldos de vacaciones',
            'type': 'ir.actions.act_window',
            'res_model': 'employee.vacation.allocation',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
