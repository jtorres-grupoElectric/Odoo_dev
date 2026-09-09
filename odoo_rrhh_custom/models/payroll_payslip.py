from odoo import _, api, fields, models
from odoo.exceptions import UserError

LOCKED_AFTER_DRAFT_FIELDS = ('company_id', 'period_start', 'period_end', 'exchange_rate_date')


class PayrollPayslip(models.Model):
    _name = 'payroll.payslip'
    _description = 'Planilla Mensual'
    _inherit = ['mail.thread']
    _order = 'period_start desc, id desc'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda')
    period_start = fields.Date(string='Inicio del periodo', required=True)
    period_end = fields.Date(string='Fin del periodo', required=True)
    exchange_rate_date = fields.Date(
        string='Fecha de referencia (tasa de cambio)',
        help='Día 10 del mes para la primera quincena (periodo 1-15) o día 25 '
             'para la segunda (periodo 16 en adelante) — se completa solo al '
             'fijar el periodo, pero es editable por si hace falta forzar otra fecha.')
    exchange_rate_resolved_date = fields.Date(
        string='Fecha de tasa aplicada', compute='_compute_exchange_rate', store=True,
        help='Última fecha con tasa publicada en o antes de la fecha de referencia: '
             'el Banco Central de Honduras no publica fines de semana ni feriados, '
             'así que en esos casos se usa el último día hábil anterior.')
    exchange_rate_value = fields.Float(
        string='Tasa de cambio aplicada (Compra)', compute='_compute_exchange_rate',
        store=True, digits=(12, 4),
        help='Tasa de compra del Banco Central de Honduras en la fecha de tasa '
             'aplicada — con esta se convierte a Lempiras el salario en USD de '
             'cada línea de esta planilla.')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('calculated', 'En Observación'),
        ('approved', 'Aprobada'),
    ], string='Estado', default='draft', required=True, tracking=True)
    prepared_by_id = fields.Many2one(
        'hr.employee', string='Elaborado por', tracking=True,
        default=lambda self: self._get_current_user_employee(self.env.company))
    approved_by_id = fields.Many2one('hr.employee', string='Visto bueno de', tracking=True)
    line_ids = fields.One2many('payroll.line', 'payslip_id', string='Empleados')
    total_to_pay = fields.Monetary(string='Total a pagar', compute='_compute_totals', store=True)
    total_deductions = fields.Monetary(string='Total deducciones', compute='_compute_totals', store=True)
    total_net = fields.Monetary(string='Total neto a pagar', compute='_compute_totals', store=True)
    total_net_usd = fields.Float(
        string='Total neto a pagar (USD)', compute='_compute_totals', store=True,
        digits=(12, 2),
        help='Total neto a pagar convertido a dólares con la tasa de cambio de compra '
             'del Banco Central aplicada a esta planilla (la misma con la que se convierte '
             'a Lempiras el salario en USD de cada línea).')

    @api.depends('line_ids.total_to_pay', 'line_ids.total_deductions', 'line_ids.net_to_pay',
                 'exchange_rate_value')
    def _compute_totals(self):
        usd = self.env.ref('base.USD')
        for payslip in self:
            payslip.total_to_pay = sum(payslip.line_ids.mapped('total_to_pay'))
            payslip.total_deductions = sum(payslip.line_ids.mapped('total_deductions'))
            payslip.total_net = sum(payslip.line_ids.mapped('net_to_pay'))
            if payslip.exchange_rate_value:
                payslip.total_net_usd = payslip.total_net / payslip.exchange_rate_value
            elif payslip.company_id.currency_id:
                date = payslip.period_end or fields.Date.context_today(payslip)
                payslip.total_net_usd = payslip.company_id.currency_id._convert(
                    payslip.total_net, usd, payslip.company_id, date)
            else:
                payslip.total_net_usd = 0.0

    @api.depends('exchange_rate_date')
    def _compute_exchange_rate(self):
        History = self.env['hr.exchange.rate.history'].sudo()
        for payslip in self:
            if not payslip.exchange_rate_date:
                payslip.exchange_rate_resolved_date = False
                payslip.exchange_rate_value = 0.0
                continue
            resolved_date, rate = History.get_buy_rate_on_or_before(payslip.exchange_rate_date)
            payslip.exchange_rate_resolved_date = resolved_date
            payslip.exchange_rate_value = rate

    @api.model
    def _quincena_reference_date(self, period_start):
        """Día 10 si el periodo empieza en la primera quincena (1-15), día 25
        si empieza en la segunda (16 en adelante) — regla pedida por el
        cliente para la conversión USD → Lempiras de cada planilla."""
        target_day = 10 if period_start.day <= 15 else 25
        return period_start.replace(day=target_day)

    @api.depends('company_id.name', 'period_start', 'period_end')
    def _compute_display_name(self):
        for payslip in self:
            if payslip.company_id and payslip.period_start and payslip.period_end:
                payslip.display_name = (
                    f'{payslip.company_id.name} — {payslip.period_start} a {payslip.period_end}'
                )
            else:
                payslip.display_name = _('Nueva planilla')

    def write(self, vals):
        if any(field in vals for field in LOCKED_AFTER_DRAFT_FIELDS):
            non_draft = self.filtered(lambda p: p.state != 'draft')
            if non_draft:
                raise UserError(_(
                    'No se puede modificar la empresa ni el periodo de una planilla '
                    'una vez que salió de borrador. Vuelve a borrador primero si es necesario.'
                ))
        return super().write(vals)

    def _get_current_user_employee(self, company):
        return self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', '=', company.id),
        ], limit=1)

    def _check_group(self, group_xmlid, error_message):
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group or group not in self.env.user.groups_id:
            raise UserError(error_message)

    def _period_days(self):
        """Total de días del periodo, ambos extremos incluidos."""
        self.ensure_one()
        if not (self.period_start and self.period_end):
            return 30
        return (self.period_end - self.period_start).days + 1

    def _generate_missing_lines(self):
        """Arma los (0,0,vals) de payroll.line para los empleados activos de la
        empresa que todavía no tienen línea en esta planilla, y la lista de
        empleados que se omiten por no tener employee.salary activo vigente.
        No escribe nada: se usa tanto desde el onchange (record virtual, sin id
        real) como desde el botón (record ya guardado)."""
        self.ensure_one()
        if not (self.company_id and self.period_start and self.period_end):
            return [], self.env['hr.employee']
        period_days = self._period_days()
        rate = self.exchange_rate_value
        existing_employee_ids = self.line_ids.employee_id.ids
        employees = self.env['hr.employee'].search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
            ('id', 'not in', existing_employee_ids),
        ])
        skipped = self.env['hr.employee']
        commands = []
        for employee in employees:
            salary = self.env['employee.salary'].search([
                ('employee_id', '=', employee.id),
                ('is_active', '=', True),
            ], order='effective_date desc', limit=1)
            if not salary:
                skipped |= employee
                continue
            # Si por algún motivo no hay tasa resuelta para el periodo (ej.
            # fecha fuera del histórico cargado), se cae de vuelta a la
            # conversión propia del salario en vez de dejar el pago en 0.
            lps = (salary.base_salary * rate) if rate else salary.base_salary_lps
            unpaid = self.env['payroll.line']._incapacity_unpaid_days(
                employee, self.period_start, self.period_end)
            commands.append((0, 0, {
                'employee_id': employee.id,
                'salary_id': salary.id,
                'base_salary_usd': salary.base_salary,
                'base_salary': lps,
                'days_worked': max(0, period_days - unpaid),
            }))
        return commands, skipped

    @api.onchange('company_id', 'period_start', 'period_end')
    def _onchange_generate_lines(self):
        if self.state != 'draft':
            return
        if self.period_start:
            self.exchange_rate_date = self._quincena_reference_date(self.period_start)
        if self.period_start and self.period_end:
            period_days = self._period_days()
            rate = self.exchange_rate_value
            for line in self.line_ids:
                unpaid = self.env['payroll.line']._incapacity_unpaid_days(
                    line.employee_id, self.period_start, self.period_end)
                line.days_worked = max(0, period_days - unpaid)
                if rate:
                    line.base_salary = line.base_salary_usd * rate
        commands, skipped = self._generate_missing_lines()
        if commands:
            self.line_ids = commands
        if skipped:
            return {'warning': {
                'title': _('Empleados sin salario activo'),
                'message': _(
                    'No se generó línea de planilla para: %s (sin salario activo vigente).'
                ) % ', '.join(skipped.mapped('name')),
            }}

    def action_generate_lines(self):
        for payslip in self.filtered(lambda p: p.state == 'draft'):
            commands, skipped = payslip._generate_missing_lines()
            if commands:
                payslip.line_ids = commands
            if skipped:
                payslip.message_post(body=_(
                    'No se generó línea de planilla para: %s (sin salario activo vigente).'
                ) % ', '.join(skipped.mapped('name')))

    def action_recalculate_days(self):
        """Vuelve a poner 'Días trabajados' = días del periodo − incapacidad sin
        goce (día 4+), para las líneas cuya incapacidad se aprobó DESPUÉS de que
        la línea ya existía. 'incapacity_unpaid_days' se recalcula solo (es un
        campo computado), pero 'días_worked' es editable a mano y no se
        resincroniza automáticamente — sin este botón, un permiso aprobado tarde
        deja la planilla pagando de más (sueldo completo + "Incapacidad a
        pagar" por los mismos días)."""
        for payslip in self.filtered(lambda p: p.state == 'draft'):
            period_days = payslip._period_days()
            for line in payslip.line_ids:
                line.days_worked = max(0, period_days - line.incapacity_unpaid_days)

    def action_calculate(self):
        for payslip in self.filtered(lambda p: p.state == 'draft'):
            if not payslip.line_ids:
                raise UserError(_('Agrega al menos un empleado antes de calcular la planilla.'))
            payslip.write({'state': 'calculated'})

    def action_approve(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_socio',
            _('Solo un Dueño/Socio puede aprobar la planilla.'),
        )
        for payslip in self.filtered(lambda p: p.state == 'calculated'):
            payslip.write({
                'state': 'approved',
                'approved_by_id': payslip._get_current_user_employee(payslip.company_id).id,
            })

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_cancel_draft(self):
        self._check_group(
            'odoo_rrhh_custom.group_rrhh_especialista',
            _('Solo un Especialista RRHH puede anular una planilla.'),
        )
        non_draft = self.filtered(lambda p: p.state != 'draft')
        if non_draft:
            raise UserError(_(
                'Solo se puede anular una planilla que está en estado Borrador.'
            ))
        self.unlink()
        return self.env['ir.actions.actions']._for_xml_id(
            'odoo_rrhh_custom.action_payroll_payslip')
