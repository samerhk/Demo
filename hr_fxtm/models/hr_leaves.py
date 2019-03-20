# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from lxml import etree
from odoo.exceptions import AccessError, UserError, ValidationError


class HolidaysRequest(models.Model):
    _inherit = 'hr.leave'

    state = fields.Selection([
        ('draft', 'To Submit'),
        ('cancel', 'Cancelled'),
        ('confirm', 'To Approve'),
        ('refuse', 'Refused'),
        ('validate1', 'Second Approval'),
        ('validate2', 'Third Approval'),
        ('validate', 'Approved')
    ], string='Status', readonly=True, track_visibility='onchange', copy=False, default='confirm',
        help="The status is set to 'To Submit', when a leave request is created." +
             "\nThe status is 'To Approve', when leave request is confirmed by user." +
             "\nThe status is 'Refused', when leave request is refused by manager." +
             "\nThe status is 'Approved', when leave request is approved by manager.")

    third_approval = fields.Boolean(related='holiday_status_id.third_approval')

    @api.multi
    def action_approve(self):
        # if validation_type == 'both': this method is the first approval approval
        # if validation_type != 'both': this method calls action_validate() below
        if any(holiday.state != 'confirm' for holiday in self):
            raise UserError(_('Leave request must be confirmed ("To Approve") in order to approve it.'))

        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)

        self.filtered(lambda hol: hol.validation_type == 'both').write(
            {'state': 'validate1', 'first_approver_id': current_employee.id})

        self.filtered(lambda hol: not hol.validation_type == 'both' and not hol.third_approval).action_validate()

        self.filtered(lambda hol: not hol.validation_type == 'both' and  hol.third_approval).write(
            {'state': 'validate2', 'first_approver_id': current_employee.id})
        if not self.env.context.get('leave_fast_create'):
            self.activity_update()
        return True

    @api.multi
    def action_validate_2(self):
        # if validation_type == 'both': this method is the first approval approval
        # if validation_type != 'both': this method calls action_validate() below
        self.filtered(lambda hol: hol.third_approval == True).write(
                {'state': 'validate2'})
        self.filtered(lambda hol: hol.validation_type == 'both').action_validate()
        if not self.env.context.get('leave_fast_create'):
            self.activity_update()

    @api.multi
    def action_validate(self):
        current_employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if any(holiday.state not in ['confirm', 'validate1', 'validate2'] for holiday in self):
            raise UserError(_('Leave request must be confirmed in order to approve it.'))

        self.write({'state': 'validate'})
        self.filtered(lambda holiday: holiday.validation_type == 'both').write(
            {'second_approver_id': current_employee.id})
        self.filtered(lambda holiday: holiday.validation_type != 'both').write(
            {'first_approver_id': current_employee.id})

        for holiday in self.filtered(lambda holiday: holiday.holiday_type != 'employee'):
            if holiday.holiday_type == 'category':
                employees = holiday.category_id.employee_ids
            elif holiday.holiday_type == 'company':
                employees = self.env['hr.employee'].search([('company_id', '=', holiday.mode_company_id.id)])
            else:
                employees = holiday.department_id.member_ids

            if self.env['hr.leave'].search_count(
                    [('date_from', '<=', holiday.date_to), ('date_to', '>', holiday.date_from),
                     ('state', 'not in', ['cancel', 'refuse']), ('holiday_type', '=', 'employee'),
                     ('employee_id', 'in', employees.ids)]):
                raise ValidationError(_('You can not have 2 leaves that overlaps on the same day.'))

            values = [holiday._prepare_holiday_values(employee) for employee in employees]
            leaves = self.env['hr.leave'].with_context(
                tracking_disable=True,
                mail_activity_automation_skip=True,
                leave_fast_create=True,
            ).create(values)
            leaves.action_approve()
            # FIXME RLi: This does not make sense, only the parent should be in validation_type both
            if leaves and leaves[0].validation_type == 'both':
                leaves.action_validate()

        employee_requests = self.filtered(lambda hol: hol.holiday_type == 'employee')
        employee_requests._validate_leave_request()
        if not self.env.context.get('leave_fast_create'):
            employee_requests.activity_update()
        return True
    @api.model
    def get_users(self,group_ext_id):
        module, ext_id = group_ext_id.split('.')
        self._cr.execute("""SELECT uid FROM res_groups_users_rel WHERE gid IN
                                    (SELECT res_id FROM ir_model_data WHERE module=%s AND name=%s) LIMIT 1 """,
                         (module, ext_id))
        return self.env['res.users'].browse(self._cr.fetchone())

    def _get_responsible_for_approval(self):
        if self.state == 'confirm' and self.manager_id.user_id:
            return self.manager_id.user_id
        elif self.state == 'confirm' and self.employee_id.parent_id.user_id:
            return self.employee_id.parent_id.user_id
        elif self.state == 'validate2':
            return self.get_users('hr_fxtm.group_hr_holidays_optional')
        elif self.department_id.manager_id.user_id:
            return self.department_id.manager_id.user_id
        return self.env.user

    def activity_update(self):
        to_clean, to_do = self.env['hr.leave'], self.env['hr.leave']
        for holiday in self:
            if holiday.state == 'draft':
                to_clean |= holiday
            elif holiday.state == 'confirm':
                holiday.activity_schedule(
                    'hr_holidays.mail_act_leave_approval',
                    user_id=holiday.sudo()._get_responsible_for_approval().id)
            elif holiday.state == 'validate1':
                holiday.activity_feedback(['hr_holidays.mail_act_leave_approval'])
                holiday.activity_schedule(
                    'hr_holidays.mail_act_leave_second_approval',
                    user_id=holiday.sudo()._get_responsible_for_approval().id)
            elif holiday.state == 'validate2':
                holiday.activity_feedback(['hr_holidays.mail_act_leave_approval'])
                holiday.activity_schedule(
                    'hr_holidays.mail_act_leave_second_approval',
                    user_id=holiday.sudo()._get_responsible_for_approval().id)
            elif holiday.state == 'validate':
                to_do |= holiday
            elif holiday.state == 'refuse':
                to_clean |= holiday
        if to_clean:
            to_clean.activity_unlink(
                ['hr_holidays.mail_act_leave_approval', 'hr_holidays.mail_act_leave_second_approval'])
        if to_do:
            to_do.activity_feedback(
                ['hr_holidays.mail_act_leave_approval', 'hr_holidays.mail_act_leave_second_approval'])


class HolidaysType(models.Model):
    _inherit = "hr.leave.type"

    third_approval = fields.Boolean('Additional validation required', default=False)
    third_user = fields.Many2one(
        'hr.employee', string='Additional user to Approval')


class Employee(models.Model):
    _inherit = "hr.employee"

    current_leave_state = fields.Selection(compute='_compute_leave_status', string="Current Leave Status",
                                           selection=[
                                               ('draft', 'New'),
                                               ('confirm', 'Waiting Approval'),
                                               ('refuse', 'Refused'),
                                               ('validate1', 'Waiting Second Approval'),
                                               ('validate2', 'Waiting Third Approval'),
                                               ('validate', 'Approved'),
                                               ('cancel', 'Cancelled')
                                           ])
