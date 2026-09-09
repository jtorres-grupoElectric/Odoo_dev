from datetime import timedelta

from odoo import _, api, fields, models


class PayrollLine(models.Model):
    _name = 'payroll.line'
    _description = 'Línea de Planilla'
    _order = 'id'

    payslip_id = fields.Many2one('payroll.payslip', string='Planilla', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='payslip_id.company_id', string='Empresa', store=True)
    currency_id = fields.Many2one(related='payslip_id.currency_id', string='Moneda')
    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True,
        domain="[('company_id', '=', parent.company_id)]")
    salary_id = fields.Many2one('employee.salary', string='Salario individual')
    base_salary_usd = fields.Float(
        string='Salario mensual $',
        help='Tomado directamente de "Salario en USD" en Salarios Individuales.')
    base_salary = fields.Monetary(
        string='Salario mensual L.',
        help='Tomado directamente de "Salario LPS" en Salarios Individuales — no se '
             'recalcula con una tasa de cambio propia de la planilla.')
    days_worked = fields.Integer(string='Días trabajados', default=30)
    salary_to_pay = fields.Monetary(string='Sueldo a pagar', compute='_compute_salary_to_pay', store=True)
    bonus = fields.Monetary(string='Bonificación')
    per_diem = fields.Monetary(string='Viáticos')
    retroactive = fields.Monetary(string='Retroactivo')
    incapacity_unpaid_days = fields.Integer(
        string='Días de incapacidad (día 4+)', compute='_compute_incapacity_unpaid_days',
        store=True,
        help='Días de Incapacidad aprobada dentro del periodo, a partir del 4º día '
             'de cada incapacidad (contado desde su propio inicio, no desde el '
             'inicio del periodo). Los primeros 3 días de cada incapacidad los paga '
             'la empresa igual que un día normal (no se restan de "Días trabajados"). '
             'Del 4º día en adelante sí se restan de "Días trabajados" porque se '
             'pagan aparte, repartidos entre empresa e IHSS (ver "Incapacidad a pagar").')
    incapacity_to_pay = fields.Monetary(
        string='Incapacidad a pagar', compute='_compute_incapacity_pay', store=True,
        help='Parte que paga la empresa de los días de incapacidad del 4º día en '
             'adelante: 34% del salario diario (con techo de L11,903.13, el mismo '
             'techo de RAP) más el 100% del excedente del salario diario real por '
             'encima de ese techo, si lo hay.')
    incapacity_ihss_pay = fields.Monetary(
        string='Cubre IHSS (incapacidad)', compute='_compute_incapacity_pay', store=True,
        help='Solo informativo: 66% del salario diario (con el mismo techo de '
             'L11,903.13) por cada día de incapacidad del 4º día en adelante. Lo '
             'paga el IHSS directamente al empleado, no sale de la planilla de la '
             'empresa — no se suma a ningún total.')
    holiday_worked_days = fields.Integer(
        string='Feriados trabajados', compute='_compute_holiday_worked', store=True)
    holiday_extra_pay = fields.Monetary(
        string='Pago extra por feriado', compute='_compute_holiday_worked', store=True,
        help='Un día de salario adicional por cada feriado/domingo trabajado en el '
             'periodo (el día ya pagado + este extra = doble).')
    vacation_days_taken = fields.Integer(
        string='Vacaciones en el periodo', compute='_compute_vacation_days_taken', store=True,
        help='Días de Vacaciones aprobadas dentro del periodo, solo informativo: se '
             'pagan con goce de sueldo (ya incluidos en "Días trabajados", sin '
             'descontarse) — este campo no afecta ningún cálculo, es para que quede '
             'visible en la planilla quién estuvo de vacaciones.')
    overtime_hours_diurna = fields.Float(
        string='H.E. Diurna', compute='_compute_overtime', store=True)
    overtime_hours_mixta = fields.Float(
        string='H.E. Mixta', compute='_compute_overtime', store=True)
    overtime_hours_nocturna = fields.Float(
        string='H.E. Nocturna', compute='_compute_overtime', store=True)
    overtime_hours_prolongacion = fields.Float(
        string='H.E. Prolongación', compute='_compute_overtime', store=True)
    overtime_hours_feriado = fields.Float(
        string='H.E. Días libres/feriados', compute='_compute_overtime', store=True)
    overtime_hours = fields.Float(
        string='Horas extra', compute='_compute_overtime', store=True,
        help='Total de horas de todas las solicitudes de horas extra aprobadas '
             'de este empleado con fecha dentro del periodo de esta planilla, '
             'sumando todos los tipos de jornada.')
    overtime_amount = fields.Monetary(
        string='Monto horas extra', compute='_compute_overtime', store=True,
        help='Suma, por cada solicitud aprobada del periodo, de '
             'horas × valor hora × (1 + recargo del tipo de jornada).')
    total_to_pay = fields.Monetary(string='Total a pagar', compute='_compute_total_to_pay', store=True)
    cooperative_deduction = fields.Monetary(string='Cooperativa')
    municipal_tax = fields.Monetary(string='Impuesto Municipal')
    isr = fields.Monetary(string='ISR')
    ihss_deduction = fields.Monetary(string='IHSS', compute='_compute_ihss', store=True)
    rap_deduction = fields.Monetary(string='RAP', compute='_compute_rap', store=True)
    total_deductions = fields.Monetary(string='Total deducciones', compute='_compute_total_deductions', store=True)
    net_to_pay = fields.Monetary(string='Total neto a pagar', compute='_compute_net_to_pay', store=True)
    pays_in_usd = fields.Boolean(related='salary_id.pays_in_usd', string='Pago en cuenta de dólares')
    net_to_pay_usd = fields.Float(string='Neto a pagar en $', compute='_compute_net_to_pay_usd')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for line in self:
            # Si la línea ya trae un salario que coincide con el empleado
            # (p. ej. porque payroll.payslip._generate_missing_lines ya la
            # armó completa), no se vuelve a buscar: evita que este onchange
            # se dispare en cascada sobre líneas recién creadas por el
            # onchange del padre y termine pisando esos valores con una
            # búsqueda redundante.
            if line.salary_id and line.salary_id.employee_id == line.employee_id:
                continue
            salary = self.env['employee.salary'].search([
                ('employee_id', '=', line.employee_id.id),
                ('is_active', '=', True),
            ], order='effective_date desc', limit=1)
            line.salary_id = salary
            line.base_salary_usd = salary.base_salary if salary else 0.0
            line.base_salary = salary.base_salary_lps if salary else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        # Red de seguridad del lado del servidor: si llega un empleado pero
        # sin salario en USD (0 o ausente) — sin importar la causa exacta en
        # el navegador (onchange en cascada, orden de eventos, etc.) — se
        # recalcula aquí mismo desde Salarios Individuales antes de guardar,
        # para que una línea de planilla nunca quede con el salario en cero
        # teniendo el empleado ya asignado.
        for vals in vals_list:
            employee_id = vals.get('employee_id')
            if employee_id and not vals.get('base_salary_usd'):
                salary = self.env['employee.salary'].search([
                    ('employee_id', '=', employee_id),
                    ('is_active', '=', True),
                ], order='effective_date desc', limit=1)
                if salary:
                    vals['salary_id'] = salary.id
                    vals['base_salary_usd'] = salary.base_salary
                    vals['base_salary'] = salary.base_salary_lps
        return super().create(vals_list)

    @api.depends('base_salary', 'days_worked')
    def _compute_salary_to_pay(self):
        for line in self:
            daily = line.base_salary / 30 if line.base_salary else 0.0
            line.salary_to_pay = daily * line.days_worked

    _OT_HOUR_FIELDS = {
        'diurna': 'overtime_hours_diurna',
        'mixta': 'overtime_hours_mixta',
        'nocturna': 'overtime_hours_nocturna',
        'prolongacion': 'overtime_hours_prolongacion',
        'feriado': 'overtime_hours_feriado',
    }

    @api.depends('employee_id.rrhh_overtime_ids.amount', 'employee_id.rrhh_overtime_ids.hours',
                 'employee_id.rrhh_overtime_ids.journey_type',
                 'employee_id.rrhh_overtime_ids.date', 'employee_id.rrhh_overtime_ids.state',
                 'payslip_id.period_start', 'payslip_id.period_end')
    def _compute_overtime(self):
        for line in self:
            payslip = line.payslip_id
            for hour_field in line._OT_HOUR_FIELDS.values():
                line[hour_field] = 0.0
            line.overtime_hours = 0.0
            line.overtime_amount = 0.0
            if not (line.employee_id and payslip.period_start and payslip.period_end):
                continue
            overtimes = line.employee_id.rrhh_overtime_ids.filtered(
                lambda o: o.state == 'approved'
                and payslip.period_start <= o.date <= payslip.period_end
            )
            for ot in overtimes:
                hour_field = line._OT_HOUR_FIELDS.get(ot.journey_type)
                if hour_field:
                    line[hour_field] += ot.hours
            line.overtime_hours = sum(overtimes.mapped('hours'))
            line.overtime_amount = sum(overtimes.mapped('amount'))

    @api.model
    def _incapacity_unpaid_days(self, employee, period_start, period_end):
        """Días de Incapacidad aprobada dentro del periodo que NO paga la
        empresa: del 4º día en adelante de cada incapacidad, contado desde el
        inicio de esa incapacidad (no desde el inicio del periodo — si una
        incapacidad cruza dos quincenas, los 3 días pagados no se repiten)."""
        if not (employee and period_start and period_end):
            return 0
        permissions = self.env['labor.permission'].sudo().search([
            ('employee_id', '=', employee.id),
            ('permission_type', '=', 'incapacidad'),
            ('state', '=', 'approved'),
            ('start_date', '<=', period_end),
            ('end_date', '>=', period_start),
        ])
        total = 0
        for perm in permissions:
            if not (perm.start_date and perm.end_date):
                continue
            unpaid_from = perm.start_date + timedelta(days=3)  # a partir del día 4
            lo = max(unpaid_from, period_start)
            hi = min(perm.end_date, period_end)
            if hi >= lo:
                total += (hi - lo).days + 1
        return total

    @api.depends('employee_id.rrhh_labor_permission_ids.state',
                 'employee_id.rrhh_labor_permission_ids.permission_type',
                 'employee_id.rrhh_labor_permission_ids.start_date',
                 'employee_id.rrhh_labor_permission_ids.end_date',
                 'payslip_id.period_start', 'payslip_id.period_end')
    def _compute_incapacity_unpaid_days(self):
        for line in self:
            line.incapacity_unpaid_days = self._incapacity_unpaid_days(
                line.employee_id, line.payslip_id.period_start, line.payslip_id.period_end)

    # Porcentajes fijos por ley: del 4º día de incapacidad en adelante, la
    # empresa cubre el 34% del salario diario (con techo) y el IHSS el 66%
    # restante — iguales para las 3 empresas, no configurables.
    INCAPACITY_COMPANY_PERCENTAGE = 34.0
    INCAPACITY_IHSS_PERCENTAGE = 66.0

    @api.depends('incapacity_unpaid_days', 'base_salary', 'company_id.payroll_rap_ceiling')
    def _compute_incapacity_pay(self):
        for line in self:
            days = line.incapacity_unpaid_days
            if not days:
                line.incapacity_to_pay = 0.0
                line.incapacity_ihss_pay = 0.0
                continue
            daily_salary = line.base_salary / 30 if line.base_salary else 0.0
            daily_ceiling = line.company_id.payroll_rap_ceiling / 30
            capped = min(daily_salary, daily_ceiling)
            excess = max(daily_salary - daily_ceiling, 0.0)
            company_daily = capped * line.INCAPACITY_COMPANY_PERCENTAGE / 100 + excess
            ihss_daily = capped * line.INCAPACITY_IHSS_PERCENTAGE / 100
            line.incapacity_to_pay = round(company_daily * days, 2)
            line.incapacity_ihss_pay = round(ihss_daily * days, 2)

    @api.depends('employee_id.rrhh_holiday_worked_ids.date',
                 'payslip_id.period_start', 'payslip_id.period_end', 'base_salary')
    def _compute_holiday_worked(self):
        for line in self:
            payslip = line.payslip_id
            if not (line.employee_id and payslip.period_start and payslip.period_end):
                line.holiday_worked_days = 0
                line.holiday_extra_pay = 0.0
                continue
            worked = line.employee_id.rrhh_holiday_worked_ids.filtered(
                lambda w: payslip.period_start <= w.date <= payslip.period_end)
            daily = line.base_salary / 30 if line.base_salary else 0.0
            line.holiday_worked_days = len(worked)
            line.holiday_extra_pay = daily * len(worked)

    @api.depends('salary_to_pay', 'bonus', 'per_diem', 'retroactive', 'incapacity_to_pay',
                 'overtime_amount', 'holiday_extra_pay')
    def _compute_total_to_pay(self):
        for line in self:
            line.total_to_pay = (
                line.salary_to_pay + line.bonus + line.per_diem
                + line.retroactive + line.incapacity_to_pay + line.overtime_amount
                + line.holiday_extra_pay
            )

    @api.depends('company_id.payroll_applies_ihss', 'company_id.payroll_ihss_fixed_quota')
    def _compute_ihss(self):
        for line in self:
            company = line.company_id
            line.ihss_deduction = company.payroll_ihss_fixed_quota if company.payroll_applies_ihss else 0.0

    @api.depends('base_salary', 'company_id.payroll_applies_rap',
                 'company_id.payroll_rap_ceiling', 'company_id.payroll_rap_percentage')
    def _compute_rap(self):
        for line in self:
            company = line.company_id
            if not company.payroll_applies_rap:
                line.rap_deduction = 0.0
                continue
            excess = max(line.base_salary - company.payroll_rap_ceiling, 0.0)
            line.rap_deduction = round(excess * company.payroll_rap_percentage / 100, 2)

    @api.depends('employee_id.rrhh_labor_permission_ids.state',
                 'employee_id.rrhh_labor_permission_ids.permission_type',
                 'employee_id.rrhh_labor_permission_ids.start_date',
                 'employee_id.rrhh_labor_permission_ids.end_date',
                 'payslip_id.period_start', 'payslip_id.period_end')
    def _compute_vacation_days_taken(self):
        for line in self:
            payslip = line.payslip_id
            if not (line.employee_id and payslip.period_start and payslip.period_end):
                line.vacation_days_taken = 0
                continue
            permissions = self.env['labor.permission'].sudo().search([
                ('employee_id', '=', line.employee_id.id),
                ('permission_type', '=', 'vacacion'),
                ('state', '=', 'approved'),
                ('start_date', '<=', payslip.period_end),
                ('end_date', '>=', payslip.period_start),
            ])
            total = 0
            for perm in permissions:
                lo = max(perm.start_date, payslip.period_start)
                hi = min(perm.end_date, payslip.period_end)
                if hi >= lo:
                    total += (hi - lo).days + 1
            line.vacation_days_taken = total

    @api.depends('cooperative_deduction', 'municipal_tax', 'isr', 'ihss_deduction', 'rap_deduction')
    def _compute_total_deductions(self):
        for line in self:
            line.total_deductions = (
                line.cooperative_deduction + line.municipal_tax + line.isr
                + line.ihss_deduction + line.rap_deduction
            )

    @api.depends('total_to_pay', 'total_deductions')
    def _compute_net_to_pay(self):
        for line in self:
            line.net_to_pay = line.total_to_pay - line.total_deductions

    @api.depends('net_to_pay', 'payslip_id.exchange_rate_value', 'payslip_id.period_end')
    def _compute_net_to_pay_usd(self):
        usd = self.env.ref('base.USD')
        for line in self:
            if not line.net_to_pay:
                line.net_to_pay_usd = 0.0
                continue
            # Misma tasa que usa la planilla para convertir USD → Lempiras
            # (tasa de compra del BCH del periodo); si no hay tasa resuelta se
            # cae a la conversión genérica de res.currency a la fecha de fin.
            rate = line.payslip_id.exchange_rate_value
            if rate:
                line.net_to_pay_usd = line.net_to_pay / rate
            elif line.company_id.currency_id:
                date = line.payslip_id.period_end or fields.Date.context_today(line)
                line.net_to_pay_usd = line.company_id.currency_id._convert(
                    line.net_to_pay, usd, line.company_id, date)
            else:
                line.net_to_pay_usd = 0.0

    @api.depends('employee_id.name')
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.employee_id.name or _('Nueva línea de planilla')
