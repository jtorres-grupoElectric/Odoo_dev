from odoo import _, api, fields, models
from odoo.exceptions import UserError

LOCKED_AFTER_DRAFT_FIELDS = (
    'company_id', 'department_id', 'job_profile_id', 'quantity',
    'requester_id', 'request_date', 'notes',
)


class HiringRequest(models.Model):
    _name = 'hiring.request'
    _description = 'Solicitud de Contratación'
    _inherit = ['mail.thread']
    _rec_name = 'job_profile_id'
    _order = 'request_date desc, id desc'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    department_id = fields.Many2one(
        'hr.department', string='Departamento', required=True,
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]")
    job_profile_id = fields.Many2one(
        'hr.job', string='Puesto solicitado', required=True,
        domain="['&', '|', ('company_id', '=', company_id), ('company_id', '=', False),"
               " '|', ('department_id', '=', department_id), ('department_id', '=', False)]")
    quantity = fields.Integer(string='Cantidad de plazas', required=True, default=1)
    requester_id = fields.Many2one(
        'hr.employee', string='Jefe solicitante', required=True,
        default=lambda self: self._get_current_user_employee(self.env.company))
    approver_id = fields.Many2one('hr.employee', string='Socio aprobador', tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pending_approval', 'Pendiente de aprobación'),
        ('approved', 'Aprobada'),
        ('in_search', 'En búsqueda'),
        ('contracted', 'Contratada'),
        ('cancelled', 'Cancelada'),
    ], string='Estado', default='draft', required=True, tracking=True)
    request_date = fields.Date(string='Fecha de solicitud', default=fields.Date.context_today)
    approval_date = fields.Date(string='Fecha de aprobación')
    notes = fields.Text(string='Notas')
    candidate_ids = fields.One2many('hiring.candidate', 'request_id', string='Candidatos')

    @api.onchange('department_id')
    def _onchange_department_id(self):
        if self.job_profile_id.department_id != self.department_id:
            self.job_profile_id = False

    def write(self, vals):
        if any(field in vals for field in LOCKED_AFTER_DRAFT_FIELDS):
            non_draft = self.filtered(lambda r: r.state != 'draft')
            if non_draft:
                raise UserError(_(
                    'No se puede modificar una solicitud de contratación '
                    'una vez enviada a aprobación. Anúlala y crea una nueva si es necesario.'
                ))
        return super().write(vals)

    def _get_current_user_employee(self, company):
        """El hr.employee del usuario actual puede variar según la empresa
        (multi-company): env.user.employee_id solo resuelve el de la empresa
        activa en la sesión, no la del registro. Buscamos explícitamente."""
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', company.id),
        ], limit=1)

    def action_submit(self):
        for request in self.filtered(lambda r: r.state == 'draft'):
            request.write({'state': 'pending_approval'})
            request._notify_group(
                'odoo_rrhh_custom.group_rrhh_socio',
                subject='Nueva solicitud de contratación por aprobar',
                body=f'{request.requester_id.name} solicitó contratar para el puesto '
                     f'"{request.job_profile_id.name}" ({request.department_id.name}). '
                     f'Requiere tu aprobación.',
            )

    def action_approve(self):
        for request in self.filtered(lambda r: r.state == 'pending_approval'):
            request.write({
                'state': 'approved',
                'approver_id': request._get_current_user_employee(request.company_id).id,
                'approval_date': fields.Date.context_today(request),
            })
            request._notify_group(
                'odoo_rrhh_custom.group_rrhh_especialista',
                subject='Solicitud de contratación aprobada',
                body=f'La solicitud para el puesto "{request.job_profile_id.name}" '
                     f'({request.department_id.name}) fue aprobada y está lista para búsqueda de candidatos.',
            )

    def action_start_search(self):
        rrhh_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        if not rrhh_group or rrhh_group not in self.env.user.groups_id:
            raise UserError(_(
                'Solo un Especialista RRHH puede iniciar la búsqueda de candidatos.'
            ))
        self.filtered(lambda r: r.state == 'approved').write({'state': 'in_search'})

    def action_mark_contracted(self):
        # Se dispara desde hiring.candidate.action_mark_contracted() al contratar
        # el primer candidato; idempotente si la solicitud ya está contratada.
        self.filtered(lambda r: r.state in ('approved', 'in_search')).write({'state': 'contracted'})

    def action_cancel(self):
        self.filtered(lambda r: r.state not in ('draft', 'contracted', 'cancelled')).write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def _notify_group(self, group_xmlid, subject, body):
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group or not group.users:
            return
        self.message_notify(
            subject=subject,
            body=body,
            partner_ids=group.users.mapped('partner_id').ids,
        )
