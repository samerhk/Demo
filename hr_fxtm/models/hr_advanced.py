


from odoo import models, fields, api, _
from lxml import etree
from odoo.exceptions import AccessError, UserError, ValidationError


class HolidaysRequest(models.Model):
    _inherit = 'salary.advance'


    @api.onchange('employee_id')
    def _employee_onchange(self):

        self.employee_contract_id = self.env['hr.contract'].search_read([('employee_id','=',self.employee_id.id)],limit=1)


