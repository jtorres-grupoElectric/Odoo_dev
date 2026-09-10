#!/usr/bin/env bash
#
# Diagnóstico del tipo de cambio USD -> LPS que usa la ficha "Salario individual".
#
# Corré este script en PRODUCCION y en PRUEBA y compará las dos salidas.
# No modifica nada: solo lee y muestra.
#
# Uso (desde la raíz del repo, en el servidor):
#     bash scripts/diagnostico_tasa.sh
#
# En prueba, para apuntar a esa base:
#     ODOO_DB=odoo18_prueba bash scripts/diagnostico_tasa.sh
#
# Overrides opcionales:
#     ODOO_CONTAINER=nombre_contenedor  ODOO_DB=nombre_base  bash scripts/diagnostico_tasa.sh
#
set -uo pipefail

DB="${ODOO_DB:-odoo18}"
CONTAINER="${ODOO_CONTAINER:-}"

if [ -z "$CONTAINER" ]; then
  CONTAINER=$(docker ps --format '{{.Names}}' | grep -Ei 'web$|odoo' | grep -vi 'db' | head -n1 || true)
fi
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no pude detectar el contenedor de Odoo." >&2
  docker ps --format '  {{.Names}}  ({{.Image}})' >&2
  echo "Volvé a correr indicándolo:  ODOO_CONTAINER=<nombre> bash scripts/diagnostico_tasa.sh" >&2
  exit 1
fi

echo ">> Contenedor Odoo: $CONTAINER"
echo ">> Base de datos:   $DB"
echo

docker exec -i "$CONTAINER" odoo shell -d "$DB" --no-http <<'PYEOF'
from odoo import fields

today = fields.Date.context_today(env['res.company'])
USD = env['res.currency'].search([('name', '=', 'USD')], limit=1)
HNL = env['res.currency'].search([('name', '=', 'HNL')], limit=1)
Rate = env['res.currency.rate']
Hist = env['hr.exchange.rate.history']

print('=' * 70)
print('FECHA DE HOY:', today)
print('=' * 70)

print('\n--- MONEDAS ---')
for cur in (USD, HNL):
    if cur:
        print('  %-4s id=%-4s activa=%s  redondeo=%s' % (
            cur.name, cur.id, cur.active, cur.rounding))
    else:
        print('  (no existe registro de moneda para ese código)')

print('\n--- MONEDA PRINCIPAL POR EMPRESA ---')
for comp in env['res.company'].search([]):
    print('  %-30s -> %s (id=%s)' % (
        comp.name, comp.currency_id.name, comp.currency_id.id))

print('\n--- res.currency.rate PARA HNL (ultimas 5, por empresa) ---')
if HNL:
    rates = Rate.search([('currency_id', '=', HNL.id)], order='name desc', limit=15)
    if not rates:
        print('  (NINGUNA fila de tasa para HNL)  <-- probable causa')
    for r in rates:
        comp = r.company_id.name if r.company_id else '(todas)'
        print('  fecha=%s  rate=%s  company=%s' % (r.name, r.rate, comp))

print('\n--- res.currency.rate PARA USD (ultimas 5, por empresa) ---')
if USD:
    rates = Rate.search([('currency_id', '=', USD.id)], order='name desc', limit=15)
    if not rates:
        print('  (NINGUNA fila de tasa para USD)')
    for r in rates:
        comp = r.company_id.name if r.company_id else '(todas)'
        print('  fecha=%s  rate=%s  company=%s' % (r.name, r.rate, comp))

print('\n--- hr.exchange.rate.history (Banco Central, ultimas 3) ---')
h = Hist.search([], order='date desc', limit=3)
if not h:
    print('  (VACIO - no se cargo el historico del BCH)')
for rec in h:
    print('  fecha=%s  compra=%s  venta=%s' % (rec.date, rec.buy_rate, rec.sell_rate))
print('  total filas:', Hist.search_count([]))

print('\n--- PRUEBA REAL DE CONVERSION (100 USD -> moneda de cada empresa) ---')
for comp in env['res.company'].search([]):
    try:
        val = USD._convert(100.0, comp.currency_id, comp, today)
        estado = 'OK' if abs(val - 100.0) > 0.01 or comp.currency_id == USD else 'NO CONVIERTE (factor 1.0)'
        print('  %-30s 100 USD = %10.2f %s   %s' % (
            comp.name, val, comp.currency_id.name, estado))
    except Exception as e:
        print('  %-30s ERROR: %s' % (comp.name, e))

print('\n--- SALARIOS ACTIVOS Y SU base_salary_lps ---')
sals = env['employee.salary'].search([('is_active', '=', True)], limit=20)
for s in sals:
    print('  %-25s USD=%9.2f  LPS=%12.2f  fecha_efectiva=%s  empresa=%s' % (
        s.employee_id.name, s.base_salary, s.base_salary_lps,
        s.effective_date, s.company_id.name))
if not sals:
    print('  (sin salarios activos)')

print('\n' + '=' * 70)
print('FIN DEL DIAGNOSTICO')
print('=' * 70)
PYEOF
