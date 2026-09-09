from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Tipos de jornada y el campo de porcentaje de recargo que le corresponde en
# res.company (Código del Trabajo de Honduras).
JOURNEY_TYPES = [
    ('diurna', 'Jornada Diurna'),
    ('mixta', 'Jornada Mixta'),
    ('nocturna', 'Jornada Nocturna'),
    ('prolongacion', 'Jornada Prolongación'),
    ('feriado', 'Días libres o feriados'),
]
JOURNEY_PCT_FIELD = {
    'diurna': 'payroll_ot_pct_diurna',
    'mixta': 'payroll_ot_pct_mixta',
    'nocturna': 'payroll_ot_pct_nocturna',
    'prolongacion': 'payroll_ot_pct_prolongacion',
    'feriado': 'payroll_ot_pct_feriado',
}


class EmployeeOvertime(models.Model):
    _name = 'employee.overtime'
    _description = 'Horas Extra'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True,
        default=lambda self: self._get_current_user_employee(self.env.company))
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    hours = fields.Float(string='Horas', required=True)
    # 194.85 = jornada mensual efectiva acordada con el cliente, usada para
    # derivar el valor de la hora a partir del salario en Lempiras (Salario
    # LPS de Salarios Individuales, no el salario en USD); el valor queda
    # editable para ajustes manuales.
    hourly_rate = fields.Float(string='Valor de la hora')
    journey_type = fields.Selection(
        JOURNEY_TYPES, string='Tipo de jornada', default='diurna',
        required=True, tracking=True,
        help='Determina el recargo aplicado sobre el valor de la hora ordinaria. '
             'Los porcentajes se configuran por empresa en Planilla (RRHH).')
    surcharge_percentage = fields.Float(
        string='Recargo (%)', compute='_compute_amount', store=True,
        help='Porcentaje de recargo de la empresa para este tipo de jornada.')
    amount = fields.Float(string='Monto', compute='_compute_amount', store=True)
    justification = fields.Text(string='Justificación')
    approver_id = fields.Many2one('hr.employee', string='Aprobado por Jefe', tracking=True)
    rrhh_approver_id = fields.Many2one('hr.employee', string='Aprobado por RRHH', tracking=True)
    state = fields.Selection([
        ('requested', 'Solicitado'),
        ('approved_jefe', 'Aprobado por Jefe'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='requested', required=True, tracking=True)
    source = fields.Selection([
        ('manual', 'Manual'),
        ('attendance_import', 'Reporte de asistencia'),
    ], string='Origen', default='manual', required=True,
        help='"Reporte de asistencia" = creado por la carga masiva desde el '
             'reporte semanal del marcador.')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for overtime in self:
            if overtime.employee_id.company_id:
                overtime.company_id = overtime.employee_id.company_id
            salary = self.env['employee.salary'].search([
                ('employee_id', '=', overtime.employee_id.id),
                ('is_active', '=', True),
            ], order='effective_date desc', limit=1)
            overtime.hourly_rate = salary.base_salary_lps / 194.85 if salary else 0.0

    @api.depends('hours', 'hourly_rate', 'journey_type',
                 'company_id.payroll_ot_pct_diurna', 'company_id.payroll_ot_pct_mixta',
                 'company_id.payroll_ot_pct_nocturna',
                 'company_id.payroll_ot_pct_prolongacion',
                 'company_id.payroll_ot_pct_feriado')
    def _compute_amount(self):
        for overtime in self:
            company = overtime.company_id or self.env.company
            pct_field = JOURNEY_PCT_FIELD.get(overtime.journey_type, 'payroll_ot_pct_diurna')
            pct = company[pct_field] if company else 0.0
            overtime.surcharge_percentage = pct
            overtime.amount = overtime.hours * overtime.hourly_rate * (1 + pct / 100)

    @api.depends('employee_id.name', 'date')
    def _compute_display_name(self):
        for overtime in self:
            overtime.display_name = ' - '.join(filter(None, [
                overtime.employee_id.name,
                f'{overtime.hours}h ({overtime.date})' if overtime.date else None,
            ])) or _('Nueva hora extra')

    def _get_current_user_employee(self, company):
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        overtimes = super().create(vals_list)
        # La carga masiva crea las horas extra ya aprobadas por RRHH: no pasa
        # por el jefe, así que no se dispara la notificación de solicitud.
        if not self.env.context.get('overtime_bulk_import'):
            for overtime in overtimes:
                overtime._notify_department_head()
        return overtimes

    def _check_group(self, group_xmlid, error_message):
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group or group not in self.env.user.groups_id:
            raise UserError(error_message)

    def action_approve(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_jefe_departamento',
            _('Solo un Jefe de Departamento puede aprobar horas extra.'),
        )
        for overtime in self.filtered(lambda o: o.state == 'requested'):
            overtime.write({
                'state': 'approved_jefe',
                'approver_id': overtime._get_current_user_employee(overtime.company_id).id,
            })
            overtime._notify_rrhh()

    def action_approve_rrhh(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_especialista',
            _('Solo un Especialista RRHH puede dar la aprobación final de horas extra.'),
        )
        for overtime in self.filtered(lambda o: o.state == 'approved_jefe'):
            overtime.write({
                'state': 'approved',
                'rrhh_approver_id': overtime._get_current_user_employee(overtime.company_id).id,
            })

    def action_reject(self):
        jefe_group = self.env.ref('odoo_rrhh_custom.group_rrhh_jefe_departamento', raise_if_not_found=False)
        especialista_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        user_groups = self.env.user.groups_id
        if (jefe_group not in user_groups) and (especialista_group not in user_groups):
            raise UserError(_(
                'Solo un Jefe de Departamento o un Especialista RRHH pueden rechazar horas extra.'
            ))
        for overtime in self:
            if overtime.state == 'requested' and jefe_group in user_groups:
                overtime.write({
                    'state': 'rejected',
                    'approver_id': overtime._get_current_user_employee(overtime.company_id).id,
                })
            elif overtime.state == 'approved_jefe' and especialista_group in user_groups:
                overtime.write({
                    'state': 'rejected',
                    'rrhh_approver_id': overtime._get_current_user_employee(overtime.company_id).id,
                })

    def _notify_department_head(self):
        self.ensure_one()
        manager = self.employee_id.department_id.manager_id
        partner = manager.user_id.partner_id if manager else False
        if not partner:
            return
        self.message_notify(
            subject='Nueva solicitud de horas extra',
            body=f'{self.employee_id.name} solicitó {self.hours}h extra el {self.date}. '
                 f'Requiere tu aprobación.',
            partner_ids=partner.ids,
        )

    def _notify_rrhh(self):
        self.ensure_one()
        group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        partners = group.users.mapped('partner_id') if group else self.env['res.partner']
        if not partners:
            return
        self.message_notify(
            subject='Horas extra pendientes de aprobación final',
            body=f'Las horas extra de {self.employee_id.name} ({self.hours}h el {self.date}) '
                 f'fueron aprobadas por su jefe y requieren tu aprobación final.',
            partner_ids=partners.ids,
        )
