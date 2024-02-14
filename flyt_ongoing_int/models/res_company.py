# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    activate_ongoing = fields.Boolean()
    ongoing_username = fields.Char()
    ongoing_password = fields.Char()
    ongoing_good_owner_code = fields.Char(string='Good Owner Code')
    last_inbound_sync = fields.Datetime()
