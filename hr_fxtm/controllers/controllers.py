# -*- coding: utf-8 -*-
from odoo import http

# class HrFxtm(http.Controller):
#     @http.route('/hr_fxtm/hr_fxtm/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/hr_fxtm/hr_fxtm/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('hr_fxtm.listing', {
#             'root': '/hr_fxtm/hr_fxtm',
#             'objects': http.request.env['hr_fxtm.hr_fxtm'].search([]),
#         })

#     @http.route('/hr_fxtm/hr_fxtm/objects/<model("hr_fxtm.hr_fxtm"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('hr_fxtm.object', {
#             'object': obj
#         })