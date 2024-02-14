from odoo import fields, models, _
from odoo.exceptions import UserError
from .ongoing_wms_request import OngoingRequest


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'ongoing.logger.mixin']

    flyt_so_ordered_by_contact = fields.Many2one('res.partner', string='Ordered by Contact')
    flyt_so_shipping_street = fields.Char('Shipping Street')
    flyt_so_shipping_co_or_company_name = fields.Char('Shipping C/O or Company Name')
    flyt_so_shipping_postal_code = fields.Char('Shipping Postal Code')
    flyt_so_shipping_city = fields.Char('Shipping City')
    flyt_so_reservation = fields.Char('Reservation')

    def action_confirm(self):
        for order in self:
            order.action_sync_product()
        result = super(SaleOrder, self).action_confirm()
        return result

    def _check_validation_article(self):
        if any(not p.default_code for p in self.order_line.mapped('product_id')):
            raise UserError(_('Internal Reference on product is missing'))

    def _prepare_article_datas(self):
        return [
            {
                'name': l.product_id.name,
                'default_code': l.product_id.default_code,
                'barcode': l.product_id.barcode,
                'price': l.price_unit,
                'uom': l.product_uom.name,
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
