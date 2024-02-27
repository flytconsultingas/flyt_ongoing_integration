# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields, _


DEFAULT_API_URL = 'https://api.ongoingsystems.se/colliflow/service.asmx?WSDL'

class ResCompany(models.Model):
    _inherit = 'res.company'

    # orig self.client = Client('https://api.ongoingsystems.se/servicelogistikk/service.asmx?WSDL')
    # https: // colliflow.ongoingsystems.se
    # self.client = Client('https://colliflow.ongoingsystems.se/servicelogistikk/service.asmx?WSDL')

    activate_ongoing = fields.Boolean()
    ongoing_sync_serial_numbers = fields.Boolean(string="Synchronize serial numbers", default=False)
    ongoing_use_shipping_name = fields.Boolean(string="Use shipping address name instead of customer name", default=False)
    ongoing_username = fields.Char()
    ongoing_password = fields.Char()
    ongoing_url = fields.Char(string='URL to Ongoing WMS api', default=DEFAULT_API_URL)
    ongoing_good_owner_code = fields.Char(string='Good Owner Code')
    last_inbound_sync = fields.Datetime()
