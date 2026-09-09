import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHiringFinalize(TransactionCase):
    """Flujo Contratado -> Finalizado: creación del perfil al final,
    status general automático y protección de borrado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        # El usuario de la prueba necesita los grupos que exigen los botones.
        cls.env.user.groups_id |= (
            cls.env.ref('odoo_rrhh_custom.group_rrhh_especialista')
            | cls.env.ref('odoo_rrhh_custom.group_rrhh_socio')
            | cls.env.ref('odoo_rrhh_custom.group_rrhh_jefe_departamento')
        )
        cls.dept = cls.env['hr.department'].create({
            'name': 'Departamento Prueba', 'company_id': False,
        })
        cls.job = cls.env['hr.job'].create({
            'name': 'Puesto Prueba', 'department_id': cls.dept.id,
        })
        cls.requester = cls.env['hr.employee'].create({
            'name': 'Jefe Solicitante', 'company_id': cls.company.id,
        })

    def _new_request(self):
        request = self.env['hiring.request'].create({
            'company_id': self.company.id,
            'department_id': self.dept.id,
            'job_profile_id': self.job.id,
            'quantity': 1,
            'requester_id': self.requester.id,
        })
        request.action_submit()
        request.action_approve()
        request.action_start_search()
        return request

    def _new_candidate(self, request):
        candidate = self.env['hiring.candidate'].create({
            'request_id': request.id,
            'name': 'Candidato Prueba',
            'email': 'cand@test.test',
            'phone': '99990000',
        })
        candidate.action_filter()
        candidate.interview_date = '2026-01-15 10:00:00'
        candidate.action_mark_interviewed()
        candidate.action_approve()
        return candidate

    # ------------------------------------------------------------------

    def test_approve_no_crea_empleado(self):
        candidate = self._new_candidate(self._new_request())
        self.assertEqual(candidate.state, 'approved')
        self.assertFalse(candidate.employee_id,
                         'action_approve() no debe crear el hr.employee')

    def test_contratado_siembra_docs_y_mueve_solicitud(self):
        request = self._new_request()
        candidate = self._new_candidate(request)
        candidate.action_mark_contracted()

        self.assertEqual(candidate.state, 'contracted')
        self.assertEqual(request.state, 'contracted',
                         'la solicitud pasa sola a "Contratada" con el primer contratado')
        self.assertEqual(
            sorted(candidate.document_ids.mapped('document_type')),
            sorted(['DNI']))
        self.assertTrue(all(candidate.document_ids.mapped('mandatory')))
        self.assertEqual(candidate.profile_department_id, self.dept)
        self.assertEqual(candidate.profile_job_id, self.job)
        self.assertTrue(candidate.profile_hire_date)
        self.assertTrue(candidate.profile_wage_effective_date)

    def test_finalizar_bloquea_si_faltan_obligatorios(self):
        candidate = self._new_candidate(self._new_request())
        candidate.action_mark_contracted()
        with self.assertRaises(UserError):
            candidate.action_finalize()
        self.assertEqual(candidate.state, 'contracted')
        self.assertFalse(candidate.employee_id)

    def test_finalizar_crea_perfil_salario_y_documentos(self):
        candidate = self._new_candidate(self._new_request())
        candidate.action_mark_contracted()

        # Adjuntar un archivo a la línea de DNI para probar la migración.
        dni = candidate.document_ids.filtered(lambda d: d.document_type == 'DNI')
        dni.write({
            'attachment': base64.b64encode(b'contenido-dni'),
            'attachment_filename': 'dni.pdf',
        })

        candidate.write({
            'profile_identification_id': '0801-1990-12345',
            'profile_birthday': '1990-05-10',
            'profile_gender': 'male',
            'profile_marital': 'single',
            'profile_private_phone': '99997777',
            'profile_wage': 600000.0,
            'profile_wage_usd': 25000.0,
            'profile_pays_in_usd': True,
            'profile_rtn': '08011990123451',
        })
        candidate.action_finalize()

        self.assertEqual(candidate.state, 'finalized')
        employee = candidate.employee_id
        self.assertTrue(employee)
        self.assertEqual(employee.name, 'Candidato Prueba')
        self.assertEqual(employee.identification_id, '0801-1990-12345')
        self.assertEqual(employee.department_id, self.dept)
        self.assertEqual(employee.job_id, self.job)
        self.assertEqual(employee.rrhh_rtn, '08011990123451')
        self.assertEqual(employee.rrhh_hire_date, candidate.profile_hire_date)

        salaries = employee.rrhh_salary_ids
        self.assertEqual(len(salaries), 1)
        self.assertEqual(salaries.base_salary, 25000.0)
        self.assertTrue(salaries.is_active)
        self.assertTrue(salaries.pays_in_usd)

        doc_request = employee.rrhh_document_request_ids
        self.assertEqual(len(doc_request), 1)
        self.assertEqual(
            sorted(doc_request.document_line_ids.mapped('document_type')),
            sorted(['DNI']))
        migrated = doc_request.document_line_ids.filtered(
            lambda l: l.document_type == 'DNI')
        self.assertTrue(migrated.attachment)
        self.assertTrue(migrated.received)

    def test_contacto_candidato_prellena_perfil(self):
        request = self._new_request()
        candidate = self.env['hiring.candidate'].create({
            'request_id': request.id,
            'name': 'Con Contacto',
            'email': 'con.contacto@test.test',
            'phone': '2222-3333',
            'id_document': '0801-2000-00001',
        })
        self.assertEqual(candidate.profile_private_email, 'con.contacto@test.test')
        self.assertEqual(candidate.profile_private_phone, '2222-3333')
        self.assertEqual(candidate.profile_identification_id, '0801-2000-00001')
        # write posterior tambien rellena si el perfil sigue vacio
        candidate2 = self.env['hiring.candidate'].create({
            'request_id': request.id, 'name': 'Sin Contacto',
        })
        self.assertFalse(candidate2.profile_private_email)
        candidate2.write({'email': 'otro@test.test'})
        self.assertEqual(candidate2.profile_private_email, 'otro@test.test')
        # no pisa un valor ya puesto a mano en el perfil
        candidate2.profile_private_phone = '9999-9999'
        candidate2.write({'phone': '1111-1111'})
        self.assertEqual(candidate2.profile_private_phone, '9999-9999')

    def test_previsualizar_documento(self):
        candidate = self._new_candidate(self._new_request())
        doc = candidate.document_ids[:1]
        self.assertTrue(doc, 'la checklist de documentos se siembra al crear el candidato')
        with self.assertRaises(UserError):
            doc.action_preview_document()
        doc.write({
            'attachment': base64.b64encode(b'%PDF-1.4 contenido'),
            'attachment_filename': 'cedula.pdf',
        })
        action = doc.action_preview_document()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['target'], 'new')
        self.assertIn('download=false', action['url'])
        self.assertIn('id=%s' % doc.id, action['url'])

    def test_no_se_puede_agregar_candidato_con_solicitud_contratada(self):
        request = self._new_request()
        # Antes de contratar, agregar candidatos funciona.
        self._new_candidate(request)
        candidate = self._new_candidate(request)
        candidate.action_mark_contracted()
        self.assertEqual(request.state, 'contracted')
        with self.assertRaises(UserError):
            self.env['hiring.candidate'].create({
                'request_id': request.id, 'name': 'Candidato Tardío',
            })

    def test_no_se_puede_borrar_contratado_ni_finalizado(self):
        # Borrable antes de "Contratado".
        candidate = self._new_candidate(self._new_request())
        candidate.unlink()
        self.assertFalse(candidate.exists())

        # No borrable en "Contratado".
        contracted = self._new_candidate(self._new_request())
        contracted.action_mark_contracted()
        with self.assertRaises(UserError):
            contracted.unlink()
        self.assertTrue(contracted.exists())

        # No borrable en "Finalizado".
        contracted.write({
            'profile_identification_id': '0801-1990-55555',
            'profile_birthday': '1988-01-01',
            'profile_gender': 'female',
            'profile_marital': 'married',
            'profile_private_phone': '88886666',
            'profile_wage': 720000.0,
            'profile_wage_usd': 30000.0,
        })
        contracted.action_finalize()
        self.assertEqual(contracted.state, 'finalized')
        with self.assertRaises(UserError):
            contracted.unlink()
        self.assertTrue(contracted.exists())
