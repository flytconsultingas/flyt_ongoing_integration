# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    fh_transport_service_code = fields.Char(string="Transporter Service Code")
