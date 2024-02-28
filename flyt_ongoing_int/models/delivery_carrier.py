# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    fh_transport_service_code = fields.Char(string="Transporter Service Code")
    transport_service_code = fields.Char(string="Transporter Service Code", compute='_calc_transport_service_code')

    @api.depends('fh_transport_service_code')
    def _calc_transport_service_code(self):
        for record in self:
            if record.fh_transport_service_code:
                record.transport_service_code = record.fh_transport_service_code
            else:
                alle = self.search([('id', '!=', record.id)])
                alle_andre = dict([(x.fh_transport_service_code, x.name) for x in alle if x.name])
                codelen = 1
                while record.name[:codelen] in alle_andre.keys() and codelen < len(record.name):
                    codelen += 1
                record.transport_service_code = record.name[:codelen]
                if not record.transport_service_code:
                    raise UserWarning(_('Empty service code for carrier %s'), record.id)




