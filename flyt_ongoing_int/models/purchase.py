# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, api, fields, registry, SUPERUSER_ID, _
from odoo.exceptions import UserError
from .ongoing_wms_request import OngoingRequest

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'ongoing.logger.mixin']

    def button_approve(self, force=False):
        for order in self:
            order.action_sync_product()
        result = super(PurchaseOrder, self).button_approve(force=force)
        return result

    def _create_picking(self):
        result = super(PurchaseOrder, self)._create_picking()
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel'] and p.picking_type_code == 'incoming')
            if pickings:
                pickings[0].action_sync_in_order()
        return result

    def _check_validation_article(self):
        if any(not p.default_code for p in self.order_line.mapped('product_id')):
            raise UserError(_('Internal Reference on product is missing'))

    def _prepare_supplier_data(self, partner_id):
        return {
            'partner_id': partner_id.id,
            'name': partner_id.name,
            'street': partner_id.street or '',
            'street2': partner_id.street2 or '',
            'zip': (partner_id.state_id and partner_id.state_id.code + ' ' or '') + (partner_id.zip or ''),
            'city': partner_id.city or '',
            'phone': partner_id.phone or '',
            'email': partner_id.email or '',
            'mobile': partner_id.mobile or '',
            'country_code': partner_id.country_code or 'NO',
            'remark': partner_id.comment or '',
        }
    def _prepare_all_supplier_data(self, product):
        if not product.seller_ids:
            return None

        return [
            self._prepare_supplier_data(s.partner_id)
        for s in product.seller_ids ]

    def _prepare_article_datas(self):
        """ Called from purchase """
        return [
            {
                'name': l.product_id.name,
                'default_code': l.product_id.default_code,
                'barcode': l.product_id.barcode,
                'price': l.price_unit,
                'uom': l.product_uom.name,
                'supplier': self._prepare_supplier_data(l.partner_id),
                'alternate_suppliers': self._prepare_all_supplier_data(l.product_id)
            } for l in self.order_line]

    def action_sync_product(self):
        self.ensure_one()
        # don't do anything is ongoing service is not activate on company
        if not self.company_id.activate_ongoing:
            return True
        self._check_validation_article()
        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            raise UserError(_('Credential Missing'))
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        for data in self._prepare_article_datas():
            response = request.process_article(data)
            if not response.get('success'):
                _logger.error('Error updating inorder line %s', data['name'])
                message = response.get('message', '')
                if response.get('error_message'):
                    message = message + '\n' + response['error_message']
                raise UserError(message)
        self.last_sync_on = fields.Datetime.now()
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Successfully sync with ongoing',
                'type': 'rainbow_man',
            }
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _update_move_date_deadline(self, new_date):
        res = super()._update_move_date_deadline(new_date)
        move_to_update = self.move_ids.filtered(lambda m: m.state not in ['done', 'cancel'])
        if move_to_update:
            pickings = move_to_update.mapped('picking_id')
            pickings.write({'scheduled_date': new_date})
        return res
