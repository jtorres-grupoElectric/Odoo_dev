from odoo import api, fields, models


class EmployeeDocumentRequest(models.Model):
    _name = 'employee.document.request'
    _description = 'Solicitud de Documentos'
    _inherit = ['mail.thread']
    _order = 'request_date desc, id desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    request_date = fields.Date(string='Fecha de solicitud', default=fields.Date.context_today)
    expected_delivery_date = fields.Date(string='Fecha esperada de entrega')
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('partial', 'Parcial'),
        ('complete', 'Completo'),
        ('verified', 'Verificado'),
    ], string='Estado', default='pending', required=True, tracking=True, compute='_compute_state', store=True)
    document_line_ids = fields.One2many(
        'employee.document.line', 'request_id', string='Documentos')

    @api.depends('document_line_ids.received', 'document_line_ids.verified')
    def _compute_state(self):
        for request in self:
            lines = request.document_line_ids
            if not lines:
                request.state = 'pending'
            elif all(line.verified for line in lines):
                request.state = 'verified'
            elif all(line.received for line in lines):
                request.state = 'complete'
            elif any(line.received for line in lines):
                request.state = 'partial'
            else:
                request.state = 'pending'


class EmployeeDocumentLine(models.Model):
    _name = 'employee.document.line'
    _description = 'Línea de Documento'

    request_id = fields.Many2one(
        'employee.document.request', string='Solicitud de documentos',
        required=True, ondelete='cascade')
    document_type = fields.Char(string='Tipo de documento', required=True)
    attachment = fields.Binary(string='Archivo')
    attachment_filename = fields.Char(string='Nombre del archivo')
    received = fields.Boolean(string='Recibido')
    received_date = fields.Date(string='Fecha de recepción')
    verified = fields.Boolean(string='Verificado')
    verified_date = fields.Date(string='Fecha de verificación')
    notes = fields.Text(string='Notas')

    @api.onchange('attachment')
    def _onchange_attachment(self):
        for line in self:
            if line.attachment and not line.received:
                line.received = True

    @api.onchange('received')
    def _onchange_received(self):
        for line in self:
            line.received_date = fields.Date.context_today(line) if line.received else False
            if not line.received:
                line.verified = False

    @api.onchange('verified')
    def _onchange_verified(self):
        for line in self:
            line.verified_date = fields.Date.context_today(line) if line.verified else False
