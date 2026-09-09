FROM odoo:18.0

# El módulo odoo_rrhh_custom declara external_dependencies python: ['xlrd']
# (import de horas extra desde el reporte de asistencia .xls). La imagen
# oficial no lo trae.
USER root
RUN pip3 install --no-cache-dir --break-system-packages xlrd
USER odoo
