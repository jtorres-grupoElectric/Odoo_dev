from odoo import fields, models


class EmploymentAgency(models.Model):
    _name = 'employment.agency'
    _description = 'Agencia de Empleo'

    name = fields.Char(string='Nombre', required=True)
    contact_info = fields.Text(string='Información de contacto')
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
