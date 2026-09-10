#!/usr/bin/env bash
#
# Siembra datos de prueba en el ambiente de PRUEBA:
#   - 5 empleados en Empresa Energía con salario individual activo (en USD)
#   - usuario "Laura Dominguez"  -> grupo Especialista RRHH  (acceso total al módulo)
#   - usuario "Yenny Hernandez"  -> grupo Planillas          (solo el apartado Planillas)
#
# Uso (desde la raíz del repo, en el servidor):
#     bash scripts/seed_prueba.sh
#
# Requisitos previos:
#   - git pull
#   - actualizar el módulo:  ... odoo -d odoo18_prueba -u odoo_rrhh_custom --stop-after-init
#
# Overrides opcionales:
#     ODOO_CONTAINER=nombre_del_contenedor  ODOO_DB=nombre_base  bash scripts/seed_prueba.sh
#
set -uo pipefail

DB="${ODOO_DB:-odoo18_prueba}"
CONTAINER="${ODOO_CONTAINER:-}"

if [ -z "$CONTAINER" ]; then
  # 1) contenedor cuyo nombre termina en "web" o contiene "odoo"
  CONTAINER=$(docker ps --format '{{.Names}}' | grep -Ei 'web$|odoo' | grep -vi 'db' | head -n1 || true)
fi
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no pude detectar el contenedor de Odoo." >&2
  echo "Contenedores en ejecución:" >&2
  docker ps --format '  {{.Names}}  ({{.Image}})' >&2
  echo "Volvé a correr indicándolo:  ODOO_CONTAINER=<nombre> bash scripts/seed_prueba.sh" >&2
  exit 1
fi

echo ">> Contenedor Odoo: $CONTAINER"
echo ">> Base de datos:   $DB"
echo

docker exec -i "$CONTAINER" odoo shell -d "$DB" --no-http <<'PYEOF'
from odoo import fields

comp = env['res.company'].search([('name', 'like', 'Empresa Energ')], limit=1)
assert comp, "No se encontró la empresa 'Empresa Energ...'"
today = fields.Date.context_today(comp)
Emp, Sal, U = env['hr.employee'], env['employee.salary'], env['res.users']

print('Empresa:', comp.name, '| moneda:', comp.currency_id.name)

empleados = [
    ('Marlon Discua', 700.0),
    ('Keydi Pineda',  550.0),
    ('Oscar Zuniga',  900.0),
    ('Wendy Calix',   600.0),
    ('Bryan Funez',   650.0),
]
for name, wage in empleados:
    e = Emp.search([('name', '=', name), ('company_id', '=', comp.id)], limit=1) \
        or Emp.create({'name': name, 'company_id': comp.id})
    if not Sal.search([('employee_id', '=', e.id), ('is_active', '=', True)]):
        Sal.create({
            'employee_id': e.id, 'company_id': comp.id,
            'base_salary': wage, 'effective_date': today, 'is_active': True,
        })
    print('  empleado + salario USD:', name, wage)

def mk_user(name, login, group_xmlid):
    grp = env.ref(group_xmlid, raise_if_not_found=False)
    assert grp, ("No existe el grupo %s -- corré primero el upgrade "
                 "(-u odoo_rrhh_custom)" % group_xmlid)
    gids = [env.ref('base.group_user').id, grp.id]
    vals = {'groups_id': [(6, 0, gids)],
            'company_ids': [(6, 0, [comp.id])], 'company_id': comp.id}
    u = U.search([('login', '=', login)], limit=1)
    if u:
        u.write(vals)
    else:
        u = U.create(dict(vals, name=name, login=login, password='Prueba2026!'))
    print('  usuario:', name, '(', login, ') ->', sorted(u.groups_id.mapped('name')))

mk_user('Laura Dominguez', 'laura.dominguez@empresaenergia.test',
        'odoo_rrhh_custom.group_rrhh_especialista')
mk_user('Yenny Hernandez', 'yenny.hernandez@empresaenergia.test',
        'odoo_rrhh_custom.group_rrhh_planillas')

env.cr.commit()
print()
print('LISTO. Login de ambos usuarios / contrasena: Prueba2026!')
PYEOF
