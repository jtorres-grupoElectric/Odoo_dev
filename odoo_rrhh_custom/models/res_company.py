from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    payroll_applies_ihss = fields.Boolean(string='Aplica IHSS', default=True)
    payroll_ihss_fixed_quota = fields.Monetary(
        string='Cuota fija IHSS (empleado)', currency_field='currency_id', default=595.16,
        help='Cuota mensual fija de IHSS a cargo del empleado, aplicable cuando el '
             'salario ya supera el techo de cotización.')
    payroll_applies_rap = fields.Boolean(string='Aplica RAP', default=True)
    payroll_rap_ceiling = fields.Monetary(
        string='Techo de cotización RAP', currency_field='currency_id', default=11903.13,
        help='Salario a partir del cual se calcula el excedente sujeto a RAP.')
    payroll_rap_percentage = fields.Float(
        string='Porcentaje RAP (empleado)', default=1.5,
        help='Porcentaje aplicado al excedente sobre el techo de cotización, a cargo del empleado. '
             'El patrono aporta el mismo porcentaje.')

    # Recargos de horas extra por tipo de jornada (Código del Trabajo de Honduras).
    payroll_ot_pct_diurna = fields.Float(
        string='Recargo Jornada Diurna (%)', default=25.0,
        help='Recargo sobre el valor de la hora ordinaria para horas extra en '
             'jornada diurna.')
    payroll_ot_pct_mixta = fields.Float(
        string='Recargo Jornada Mixta (%)', default=50.0)
    payroll_ot_pct_nocturna = fields.Float(
        string='Recargo Jornada Nocturna (%)', default=75.0)
    payroll_ot_pct_prolongacion = fields.Float(
        string='Recargo Jornada Prolongación (%)', default=100.0)
    payroll_ot_pct_feriado = fields.Float(
        string='Recargo Días libres o feriados (%)', default=100.0)

    # Horario ordinario, para que la carga masiva ubique dónde empiezan las
    # horas extra. Si el empleado entra tarde, el fin de jornada se corre:
    # fin = max(entrada, inicio) + (fin - inicio).
    payroll_ordinary_start = fields.Float(
        string='Inicio jornada ordinaria', default=7.0,
        help='Hora de entrada programada, en formato decimal (7.0 = 07:00, 7.5 = 07:30).')
    payroll_ordinary_end = fields.Float(
        string='Fin jornada ordinaria (lun-vie)', default=17.0,
        help='Hora de salida programada de lunes a viernes, en formato decimal (17.0 = 17:00).')
    payroll_saturday_end = fields.Float(
        string='Fin jornada ordinaria (sábado)', default=12.0,
        help='Hora de salida programada los sábados. Lo trabajado después cuenta '
             'como hora extra. El domingo es día de descanso (100%).')

    # Bandas horarias que definen el tipo de jornada de las horas extra, contadas
    # desde el fin de jornada. Antes de "mixta desde" → Diurna.
    payroll_ot_mixta_from = fields.Float(
        string='H.E. Mixta desde', default=19.0,
        help='A partir de esta hora las horas extra son Mixtas (19.0 = 07:00 PM).')
    payroll_ot_nocturna_from = fields.Float(
        string='H.E. Nocturna desde', default=22.0,
        help='A partir de esta hora las horas extra son Nocturnas (22.0 = 10:00 PM).')
    payroll_ot_prolongacion_from = fields.Float(
        string='H.E. Prolongada desde (día siguiente)', default=5.0,
        help='Hora del día siguiente a partir de la cual las horas extra son '
             'Prolongadas (5.0 = 05:00 AM). Es el caso de trabajar toda la noche.')
