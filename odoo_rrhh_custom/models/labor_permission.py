from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LaborPermission(models.Model):
    _name = 'labor.permission'
    _description = 'Permiso Laboral'
    _inherit = ['mail.thread']
    _order = 'start_date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True,
        default=lambda self: self._get_current_user_employee(self.env.company))
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    permission_type = fields.Selection([
        ('especial', 'Permiso Especial'),
        ('laboral', 'Permiso Laboral'),
        ('vacacion', 'Vacaciones'),
        ('incapacidad', 'Ausencia por Incapacidad'),
    ], string='Tipo de permiso', required=True)
    start_date = fields.Date(string='Fecha de inicio', required=True)
    end_date = fields.Date(string='Fecha de fin', required=True)
    days_count = fields.Integer(string='Días', compute='_compute_days_count', store=True)
    vacation_balance_days = fields.Float(
        string='Saldo de vacaciones disponible', related='employee_id.rrhh_vacation_available_days')
    projected_vacation_balance = fields.Float(
        string='Saldo proyectado tras este permiso', compute='_compute_projected_vacation_balance')
    justification = fields.Text(string='Justificación')
    attachment = fields.Binary(string='Adjunto')
    attachment_filename = fields.Char(string='Nombre del adjunto')
    approver_id = fields.Many2one('hr.employee', string='Aprobado por Jefe', tracking=True)
    rrhh_approver_id = fields.Many2one('hr.employee', string='Aprobado por RRHH', tracking=True)
    state = fields.Selection([
        ('requested', 'Solicitado'),
        ('approved_jefe', 'Aprobado por Jefe'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='requested', required=True, tracking=True)

    @api.depends('employee_id.name', 'permission_type')
    def _compute_display_name(self):
        for permission in self:
            permission_type_label = dict(
                permission._fields['permission_type'].selection
            ).get(permission.permission_type, '')
            permission.display_name = ' - '.join(filter(None, [
                permission.employee_id.name, permission_type_label,
            ])) or _('Nuevo permiso laboral')

    @api.depends('start_date', 'end_date')
    def _compute_days_count(self):
        for permission in self:
            if permission.start_date and permission.end_date:
                permission.days_count = (permission.end_date - permission.start_date).days + 1
            else:
                permission.days_count = 0

    @api.depends('vacation_balance_days', 'days_count', 'permission_type')
    def _compute_projected_vacation_balance(self):
        for permission in self:
            if permission.permission_type == 'vacacion':
                permission.projected_vacation_balance = (
                    permission.vacation_balance_days - permission.days_count
                )
            else:
                permission.projected_vacation_balance = 0.0

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for permission in self:
            if permission.start_date and permission.end_date and permission.end_date < permission.start_date:
                raise ValidationError(_(
                    'La fecha de fin no puede ser anterior a la fecha de inicio.'
                ))

    @api.constrains('permission_type', 'justification', 'attachment')
    def _check_incapacidad_requires_proof(self):
        for permission in self:
            if permission.permission_type == 'incapacidad' and not (
                permission.justification and permission.attachment
            ):
                raise ValidationError(_(
                    'Una Ausencia por Incapacidad requiere justificación y '
                    'adjuntar el comprobante (constancia del IHSS u orden médica) '
                    'para poder solicitarse.'
                ))

    def _get_current_user_employee(self, company):
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        permissions = super().create(vals_list)
        for permission in permissions:
            permission._notify_department_head()
        return permissions

    def _check_group(self, group_xmlid, error_message):
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group or group not in self.env.user.groups_id:
            raise UserError(error_message)

    def action_approve(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_jefe_departamento',
            _('Solo un Jefe de Departamento puede aprobar permisos laborales.'),
        )
        for permission in self.filtered(lambda p: p.state == 'requested'):
            permission.write({
                'state': 'approved_jefe',
                'approver_id': permission._get_current_user_employee(permission.company_id).id,
            })
            permission._notify_rrhh()

    def action_approve_rrhh(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_especialista',
            _('Solo un Especialista RRHH puede dar la aprobación final del permiso laboral.'),
        )
        vacation_permissions = self.filtered(
            lambda p: p.state == 'approved_jefe' and p.permission_type == 'vacacion')
        for permission in self.filtered(lambda p: p.state == 'approved_jefe'):
            permission.write({
                'state': 'approved',
                'rrhh_approver_id': permission._get_current_user_employee(permission.company_id).id,
            })
        if vacation_permissions:
            # employee.vacation.allocation.used_days/available_days no dependen
            # formalmente de labor.permission (no hay relación inversa declarable),
            # así que el caché de esos campos no se invalida solo: se fuerza aquí
            # para que el saldo se vea correcto sin tener que recargar la sesión.
            allocations = self.env['employee.vacation.allocation'].sudo().search([
                ('employee_id', 'in', vacation_permissions.employee_id.ids),
                ('year', 'in', list(set(vacation_permissions.mapped(
                    lambda p: p.start_date.year)))),
            ])
            allocations.invalidate_recordset(['used_days', 'available_days'])

    def action_reject(self):
        jefe_group = self.env.ref('odoo_rrhh_custom.group_rrhh_jefe_departamento', raise_if_not_found=False)
        especialista_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        user_groups = self.env.user.groups_id
        if (jefe_group not in user_groups) and (especialista_group not in user_groups):
            raise UserError(_(
                'Solo un Jefe de Departamento o un Especialista RRHH pueden rechazar permisos laborales.'
            ))
        for permission in self:
            if permission.state == 'requested' and jefe_group in user_groups:
                permission.write({
                    'state': 'rejected',
                    'approver_id': permission._get_current_user_employee(permission.company_id).id,
                })
            elif permission.state == 'approved_jefe' and especialista_group in user_groups:
                permission.write({
                    'state': 'rejected',
                    'rrhh_approver_id': permission._get_current_user_employee(permission.company_id).id,
                })

    def _notify_department_head(self):
        self.ensure_one()
        manager = self.employee_id.department_id.manager_id
        partner = manager.user_id.partner_id if manager else False
        if not partner:
            return
        self.message_notify(
            subject='Nueva solicitud de permiso laboral',
            body=f'{self.employee_id.name} solicitó "{dict(self._fields["permission_type"].selection).get(self.permission_type)}" '
                 f'del {self.start_date} al {self.end_date}. Requiere tu aprobación.',
            partner_ids=partner.ids,
        )

    def _notify_rrhh(self):
        self.ensure_one()
        group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        partners = group.users.mapped('partner_id') if group else self.env['res.partner']
        if not partners:
            return
        self.message_notify(
            subject='Permiso laboral pendiente de aprobación final',
            body=f'El permiso de {self.employee_id.name} '
                 f'("{dict(self._fields["permission_type"].selection).get(self.permission_type)}") '
                 f'fue aprobado por su jefe y requiere tu aprobación final.',
            partner_ids=partners.ids,
        )
