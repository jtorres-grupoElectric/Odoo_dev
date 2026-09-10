{
    'name': 'RRHH Custom',
    'version': '18.0.1.0.4',
    'summary': 'Reclutamiento, contratación, salario individual, permisos laborales y solicitud de documentos',
    'description': """
Módulo custom de Recursos Humanos para ambiente multiempresa (Sunergy, Solargy, Empresa Energía).

Incluye:
- Flujo de reclutamiento y contratación
- Salario individual por empleado, con historial y bonos
- Horas extra con aprobación en 2 pasos (Jefe y RRHH)
- Permisos laborales, incluidas vacaciones con control de saldo real por año
- Solicitud y verificación de documentos a empleados nuevos
- Ficha del empleado ampliada con salario, vacaciones y horas extra
- Configuración de planilla por empresa (IHSS, RAP)
- Planilla mensual: cálculo de deducciones (IHSS, RAP) y neto a pagar por empleado

No incluye todavía (pendiente de módulo de Contabilidad): asientos contables de nómina.
    """,
    'category': 'Human Resources',
    'author': 'Custom Development',
    'depends': ['base', 'hr', 'hr_skills', 'mail'],
    'external_dependencies': {'python': ['xlrd']},
    'data': [
        'security/rrhh_security_groups.xml',
        'security/ir.model.access.csv',
        'security/security_rules.xml',
        'data/menu.xml',
        'data/hr_department_job_data.xml',
        'data/exchange_rate_cron.xml',
        'views/res_company_views.xml',
        'views/payroll_holiday_views.xml',
        'views/hiring_request_views.xml',
        'views/hiring_candidate_views.xml',
        'views/employment_agency_views.xml',
        'views/employee_salary_views.xml',
        'views/payroll_payslip_views.xml',
        'views/exchange_rate_config_views.xml',
        'views/labor_permission_views.xml',
        'wizard/overtime_bulk_import_views.xml',
        'views/employee_overtime_views.xml',
        'views/employee_vacation_allocation_views.xml',
        'views/employee_document_views.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_rrhh_custom/static/src/xml/chatter_patch.xml',
            'odoo_rrhh_custom/static/src/xml/simple_create_patch.xml',
            'odoo_rrhh_custom/static/src/xml/doc_preview_button.xml',
            'odoo_rrhh_custom/static/src/js/doc_preview_button.js',
            'odoo_rrhh_custom/static/src/scss/rrhh_lists.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
