from odoo import _, api, fields, models
from odoo.exceptions import UserError

DOCUMENT_TYPES_ON_HIRE = ('DNI',)

# Campos del perfil que deben estar llenos para poder finalizar y crear el
# hr.employee. (nombre_campo, etiqueta para el mensaje de error).
PROFILE_REQUIRED_FIELDS = [
    ('profile_identification_id', 'No. de Identidad (DNI)'),
    ('profile_birthday', 'Fecha de nacimiento'),
    ('profile_gender', 'Género'),
    ('profile_marital', 'Estado civil'),
    ('profile_private_phone', 'Teléfono personal'),
    ('profile_hire_date', 'Fecha de ingreso'),
    ('profile_department_id', 'Departamento'),
    ('profile_job_id', 'Puesto'),
    ('profile_wage_usd', 'Sueldo en Dólares'),
]


class HiringCandidate(models.Model):
    _name = 'hiring.candidate'
    _description = 'Candidato'
    _inherit = ['mail.thread']
    _order = 'score desc, id desc'

    request_id = fields.Many2one(
        'hiring.request', string='Solicitud de contratación', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Empresa', related='request_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    name = fields.Char(string='Nombre', required=True)
    email = fields.Char(string='Correo')
    phone = fields.Char(string='Teléfono')
    id_document = fields.Char(string='No. de Identidad (DNI)')
    agency_id = fields.Many2one(
        'employment.agency', string='Agencia de empleo',
        domain="[('company_id', '=', company_id)]")
    score = fields.Float(string='Puntuación')
    expected_salary = fields.Float(string='Salario esperado')
    interview_date = fields.Datetime(string='Fecha de entrevista')
    approver_id = fields.Many2one('hr.employee', string='Jefe que aprueba', tracking=True)
    state = fields.Selection([
        ('proposed', 'Propuesto'),
        ('filtered', 'Filtrado'),
        ('interviewed', 'Entrevistado'),
        ('approved', 'Aprobado'),
        ('contracted', 'Contratado'),
        ('finalized', 'Finalizado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='proposed', required=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado generado', readonly=True)

    # ------------------------------------------------------------------
    # Datos para el perfil — se llenan mientras el candidato está en
    # 'contracted'; al finalizar se vuelcan al hr.employee que se crea.
    # ------------------------------------------------------------------
    profile_identification_id = fields.Char(string='No. de Identidad (DNI)')
    profile_rtn = fields.Char(string='RTN')
    profile_inss_no = fields.Char(string='No. INSS')
    profile_rap_no = fields.Char(string='No. RAP')

    profile_birthday = fields.Date(string='Fecha de nacimiento')
    profile_place_of_birth = fields.Char(string='Lugar de nacimiento')
    profile_country_id = fields.Many2one('res.country', string='Nacionalidad')
    profile_gender = fields.Selection([
        ('male', 'Masculino'),
        ('female', 'Femenino'),
        ('other', 'Otro'),
    ], string='Género')
    profile_marital = fields.Selection([
        ('single', 'Soltero(a)'),
        ('married', 'Casado(a)'),
        ('cohabitant', 'Unión libre'),
        ('widower', 'Viudo(a)'),
        ('divorced', 'Divorciado(a)'),
    ], string='Estado civil')
    profile_children = fields.Integer(string='No. de hijos/dependientes')

    profile_private_street = fields.Char(string='Dirección particular')
    profile_private_city = fields.Char(string='Ciudad')
    profile_private_phone = fields.Char(string='Teléfono personal')
    profile_private_email = fields.Char(string='Correo personal')

    profile_emergency_contact = fields.Char(string='Contacto de emergencia')
    profile_emergency_relationship = fields.Char(string='Parentesco')
    profile_emergency_phone = fields.Char(string='Teléfono de emergencia')

    profile_education_level = fields.Char(string='Nivel de estudios')
    profile_study_field = fields.Char(string='Título / carrera')
    profile_study_school = fields.Char(string='Institución')

    profile_hire_date = fields.Date(string='Fecha de ingreso')
    profile_department_id = fields.Many2one('hr.department', string='Departamento')
    profile_job_id = fields.Many2one('hr.job', string='Puesto')

    profile_wage = fields.Monetary(string='Sueldo en Lempiras', currency_field='currency_id')
    profile_wage_usd = fields.Float(string='Sueldo en Dólares')
    profile_pays_in_usd = fields.Boolean(string='Pago en cuenta de dólares')
    profile_wage_effective_date = fields.Date(string='Fecha efectiva del sueldo')

    profile_bank_id = fields.Many2one('res.bank', string='Banco')
    profile_bank_account_number = fields.Char(string='No. de cuenta')

    document_ids = fields.One2many(
        'hiring.candidate.document', 'candidate_id', string='Documentación')

    def _get_current_user_employee(self, company):
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', company.id),
        ], limit=1)

    # Contacto del candidato -> contacto del perfil que se creará.
    _PROFILE_CONTACT_MAP = (
        ('email', 'profile_private_email'),
        ('phone', 'profile_private_phone'),
        ('id_document', 'profile_identification_id'),
    )

    @api.onchange('email', 'phone', 'id_document')
    def _onchange_prefill_profile_contact(self):
        """Los datos de contacto del candidato prellenan los del perfil (solo si
        el campo del perfil sigue vacío, para no pisar una edición manual)."""
        for src, dst in self._PROFILE_CONTACT_MAP:
            if self[src] and not self[dst]:
                self[dst] = self[src]

    def _prefill_profile_contact(self):
        """Misma lógica que el onchange, aplicada a nivel de ORM para que
        funcione aunque el candidato lo cree un usuario cuya vista no incluye
        los campos del perfil (p. ej. un Jefe de Departamento)."""
        for candidate in self:
            vals = {
                dst: candidate[src]
                for src, dst in candidate._PROFILE_CONTACT_MAP
                if candidate[src] and not candidate[dst]
            }
            if vals:
                super(HiringCandidate, candidate).write(vals)

    def unlink(self):
        protected = self.filtered(lambda c: c.state in ('contracted', 'finalized'))
        if protected:
            raise UserError(_(
                'No se puede borrar un candidato que ya está en "Contratado" o '
                '"Finalizado": %s.'
            ) % ', '.join(protected.mapped('name')))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        requests = self.env['hiring.request'].browse(
            [vals['request_id'] for vals in vals_list if vals.get('request_id')])
        if any(request.state in ('contracted', 'cancelled') for request in requests):
            raise UserError(_(
                'No se pueden agregar candidatos a una solicitud de contratación '
                'que ya está "Contratada" o "Cancelada".'
            ))
        candidates = super().create(vals_list)
        # La checklist de documentos está disponible desde el primer momento del
        # proceso, no solo al contratar.
        candidates._seed_default_documents()
        candidates._prefill_profile_contact()
        return candidates

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field, _dst in self._PROFILE_CONTACT_MAP):
            self._prefill_profile_contact()
        return res

    def action_filter(self):
        for candidate in self.filtered(lambda c: c.state == 'proposed'):
            candidate.state = 'filtered'
            candidate._notify_requester(
                subject='Candidato preseleccionado',
                body=f'El candidato "{candidate.name}" fue preseleccionado para '
                     f'"{candidate.request_id.job_profile_id.name}" y está listo para entrevista.',
            )

    def action_mark_interviewed(self):
        for candidate in self.filtered(lambda c: c.state == 'filtered'):
            if not candidate.interview_date:
                raise UserError(_(
                    'Agrega primero la fecha de entrevista del candidato "%s".'
                ) % candidate.name)
            candidate.state = 'interviewed'

    def action_approve(self):
        especialista_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        if not especialista_group or especialista_group not in self.env.user.groups_id:
            raise UserError(_(
                'Solo un Especialista RRHH puede aprobar candidatos.'
            ))
        for candidate in self.filtered(lambda c: c.state == 'interviewed'):
            candidate.write({
                'state': 'approved',
                'approver_id': candidate._get_current_user_employee(candidate.company_id).id,
            })

    def action_mark_contracted(self):
        today = fields.Date.context_today(self)
        for candidate in self.filtered(lambda c: c.state == 'approved'):
            vals = {'state': 'contracted'}
            # Prellenar lo que ya se conoce por la solicitud; sigue editable.
            if not candidate.profile_hire_date:
                vals['profile_hire_date'] = today
            if not candidate.profile_wage_effective_date:
                vals['profile_wage_effective_date'] = today
            if not candidate.profile_department_id:
                vals['profile_department_id'] = candidate.request_id.department_id.id
            if not candidate.profile_job_id:
                vals['profile_job_id'] = candidate.request_id.job_profile_id.id
            candidate.write(vals)
            candidate._seed_default_documents()
            # La solicitud (status general) pasa a "Contratada" con el primer
            # candidato contratado.
            candidate.request_id.action_mark_contracted()

    def action_finalize(self):
        especialista_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        if not especialista_group or especialista_group not in self.env.user.groups_id:
            raise UserError(_(
                'Solo un Especialista RRHH puede finalizar el perfil.'
            ))
        for candidate in self.filtered(lambda c: c.state == 'contracted'):
            candidate._check_profile_complete()
            # hr.employee y sus modelos hijos no tienen ACL propia en este
            # módulo: se crean con sudo(), igual que se hacía antes en
            # action_approve().
            employee = candidate._create_employee_profile()
            candidate._create_salary(employee)
            candidate._create_document_request(employee)
            candidate.sudo().write({'state': 'finalized', 'employee_id': employee.id})
            candidate._notify_requester(
                subject='Perfil de empleado creado',
                body=f'El perfil de "{candidate.name}" fue creado y el proceso de '
                     f'contratación quedó finalizado.',
            )

    def action_reject(self):
        jefe_group = self.env.ref('odoo_rrhh_custom.group_rrhh_jefe_departamento', raise_if_not_found=False)
        especialista_group = self.env.ref('odoo_rrhh_custom.group_rrhh_especialista', raise_if_not_found=False)
        user_groups = self.env.user.groups_id
        if (jefe_group not in user_groups) and (especialista_group not in user_groups):
            raise UserError(_(
                'Solo un Jefe de Departamento o un Especialista RRHH pueden rechazar candidatos.'
            ))
        candidates = self.filtered(lambda c: c.state not in ('contracted', 'finalized', 'rejected'))
        if jefe_group in user_groups and especialista_group not in user_groups:
            candidates.sudo().write({'state': 'rejected'})
        else:
            candidates.write({'state': 'rejected'})

    def _check_profile_complete(self):
        self.ensure_one()
        missing = []
        for fname, label in PROFILE_REQUIRED_FIELDS:
            value = self[fname]
            if fname == 'profile_wage_usd':
                if not value or value <= 0:
                    missing.append(label)
            elif not value:
                missing.append(label)
        if missing:
            raise UserError(_(
                'No se puede finalizar: faltan datos obligatorios del perfil:\n- %s'
            ) % '\n- '.join(missing))

    def _create_employee_profile(self):
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        vals = {
            'name': self.name,
            'company_id': self.company_id.id,
            'department_id': self.profile_department_id.id,
            'job_id': self.profile_job_id.id,
            'work_email': self.email,
            'work_phone': self.phone,
            'rrhh_hire_date': self.profile_hire_date,
            'identification_id': self.profile_identification_id,
            'birthday': self.profile_birthday,
            'place_of_birth': self.profile_place_of_birth,
            'country_id': self.profile_country_id.id,
            'gender': self.profile_gender,
            'marital': self.profile_marital,
            'children': self.profile_children,
            'private_street': self.profile_private_street,
            'private_city': self.profile_private_city,
            'private_phone': self.profile_private_phone,
            'private_email': self.profile_private_email,
            'emergency_contact': self.profile_emergency_contact,
            'emergency_phone': self.profile_emergency_phone,
            'study_field': self.profile_study_field,
            'study_school': self.profile_study_school,
            'rrhh_rtn': self.profile_rtn,
            'rrhh_inss_no': self.profile_inss_no,
            'rrhh_rap_no': self.profile_rap_no,
            'rrhh_education_level': self.profile_education_level,
            'rrhh_emergency_relationship': self.profile_emergency_relationship,
            'rrhh_bank_id': self.profile_bank_id.id,
            'rrhh_bank_account_number': self.profile_bank_account_number,
        }
        # Blindaje: si algún campo estándar de hr.employee cambió de nombre
        # entre versiones de Odoo, no romper la creación por eso.
        vals = {k: v for k, v in vals.items() if k in Employee._fields}
        return Employee.create(vals)

    def _create_salary(self, employee):
        self.ensure_one()
        self.env['employee.salary'].sudo().create({
            'employee_id': employee.id,
            'company_id': self.company_id.id,
            'base_salary': self.profile_wage_usd,
            'effective_date': self.profile_wage_effective_date or fields.Date.context_today(self),
            'pays_in_usd': self.profile_pays_in_usd,
            'is_active': True,
        })

    def _seed_default_documents(self):
        for candidate in self:
            existing = candidate.document_ids.mapped('document_type')
            missing = [d for d in DOCUMENT_TYPES_ON_HIRE if d not in existing]
            if missing:
                candidate.write({
                    'document_ids': [
                        (0, 0, {'document_type': doc_type, 'mandatory': True})
                        for doc_type in missing
                    ]
                })

    def _create_document_request(self, employee):
        self.ensure_one()
        today = fields.Date.context_today(self)
        lines = []
        for doc in self.document_ids:
            lines.append((0, 0, {
                'document_type': doc.document_type,
                'attachment': doc.attachment,
                'attachment_filename': doc.attachment_filename,
                'received': bool(doc.attachment),
                'received_date': today if doc.attachment else False,
                'notes': doc.notes,
            }))
        if not lines:
            lines = [(0, 0, {'document_type': doc_type}) for doc_type in DOCUMENT_TYPES_ON_HIRE]
        request = self.env['employee.document.request'].sudo().create({
            'employee_id': employee.id,
            'company_id': self.company_id.id,
            'document_line_ids': lines,
        })
        pending = self.document_ids.filtered(lambda d: d.mandatory and not d.attachment)
        if pending:
            self.message_post(body=_(
                'Perfil finalizado con documentos obligatorios pendientes de recibir: %s'
            ) % ', '.join(pending.mapped('document_type')))
        return request

    def _notify_requester(self, subject, body):
        for candidate in self:
            partner = candidate.request_id.requester_id.user_id.partner_id
            if not partner:
                continue
            candidate.message_notify(subject=subject, body=body, partner_ids=partner.ids)


class HiringCandidateDocument(models.Model):
    _name = 'hiring.candidate.document'
    _description = 'Documento de Candidato'

    candidate_id = fields.Many2one(
        'hiring.candidate', string='Candidato', required=True, ondelete='cascade')
    document_type = fields.Char(string='Tipo de documento', required=True)
    attachment = fields.Binary(string='Archivo')
    attachment_filename = fields.Char(string='Nombre del archivo')
    mandatory = fields.Boolean(string='Obligatorio')
    notes = fields.Text(string='Notas')

    def action_preview_document(self):
        self.ensure_one()
        if not self.attachment:
            raise UserError(_('Esta línea no tiene ningún archivo subido.'))
        if isinstance(self.id, models.NewId):
            # El botón guarda el formulario antes de llegar aquí; este aviso solo
            # aparecería si el guardado automático fallara por otra razón.
            raise UserError(_('Guarda el candidato para poder previsualizar el documento.'))
        # download=false -> Content-Disposition: inline, el navegador previsualiza
        # PDF e imágenes en una pestaña nueva sin descargar.
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content?model=hiring.candidate.document&id=%s'
                   '&field=attachment&filename_field=attachment_filename&download=false' % self.id,
            'target': 'new',
        }
