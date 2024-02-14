# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    activate_ongoing = fields.Boolean(related='company_id.activate_ongoing', readonly=False)
    ongoing_username = fields.Char(related='company_id.ongoing_username', readonly=False)
    ongoing_password = fields.Char(related='company_id.ongoing_password', readonly=False)
    ongoing_good_owner_code = fields.Char(related='company_id.ongoing_good_owner_code', readonly=False)
