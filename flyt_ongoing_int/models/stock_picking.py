# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from dateutil.relativedelta import relativedelta
import collections, functools, operator
from xml.etree import ElementTree
from zeep import helpers

from odoo import models, api, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from .ongoing_wms_request import OngoingRequest
from markupsafe import Markup


_logger = logging.getLogger(__name__)

TRACKED_ITEMS = ['FH8071']


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'ongoing.logger.mixin']

    ongoing_order_id = fields.Char(copy=False)
    flyt_location_dest_id_usage = fields.Selection(related='location_dest_id.usage', store=True)

    ongoing_sync_serial_numbers = fields.Boolean(related='company_id.ongoing_sync_serial_numbers', store=False)

    def _check_validation_inorder(self):
        partner = self.picking_type_id.warehouse_id.partner_id
        if not len(self.move_ids_without_package):
            raise UserError(_('Order line missing'))
        if any(not p.default_code for p in self.move_ids_without_package.mapped('product_id')):
            raise UserError(_('Internal Reference on product is missing'))

    def _get_lines(self):
        """ Get stock.move lines from a stock.picking. Used to send InOrder lines to Ongoing """
        lines = []
        for line in self.move_ids_without_package:
            lines.append({
                'product_code': line.product_id.default_code,
                'quantity': line.product_uom_qty,
            })
        return lines

    def _prepare_inorder_datas(self):
        partner = self.picking_type_id.warehouse_id.partner_id
        internal_transfer = self.move_ids.move_dest_ids.mapped('picking_id')
        data = {
            'order_number': self.origin,
            # 'customer_number': partner.ref,
            # 'customer_name': partner.name,
            # 'customer_address': partner.street,
            # 'customer_city': partner.city,
            # 'customer_zip': partner.zip,
            # 'customer_phone': partner.phone,
            # 'customer_mobile': partner.mobile,
            # 'customer_country': partner.country_id.code,
            'supplier_number': self.partner_id.id,
            'reference': internal_transfer.name if internal_transfer and len(internal_transfer) == 1 else self.name,
            'lines': self._get_lines(),
            'order_date': self.purchase_id.date_approve or '',
            'in_date': self.scheduled_date or '',
        }
        return data

    def action_sync_in_order(self):
        """
            This function will call from the button and is responsible for creating purchase
            order on ongoing platform
            @return - bool
        """
        # don't do anything if ongoing service is not activated on company
        if not self.company_id.activate_ongoing:
            return True
        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            raise UserError(_('Credential Missing'))
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)

        ##### Denne har utgåande også... internal_transfer = self.move_ids.move_dest_ids.mapped('picking_id') ## self = INT transfer
        internal_transfer = self.move_ids.move_dest_ids.filtered(lambda p: p.picking_type_id.code == 'internal').mapped('picking_id')

        if self.purchase_id and self.purchase_id.default_location_dest_id_usage == 'customer':
            return False

        self._check_validation_inorder()
        data = self._prepare_inorder_datas()
        response = request.process_inorder(data)
        if not response.get('success'):
            message = response.get('message', '')
            if response.get('error_message'):
                message = message + '\n' + response['error_message']
            raise UserError(message)

        self.last_sync_on = fields.Datetime.now()
        title = _('Synced with Ongoing WMS')
        message = Markup('<strong>{}</strong> <br/> <strong>In Order ID :: </strong> {} <br/> <strong>Message ::</strong> {}'.format(title, response.get('in_order_id', ''), response.get('message', '')))
        self.ongoing_order_id = response.get('in_order_id', '')
        self.message_post(body=message)

        for int_picking in internal_transfer:
            int_picking.last_sync_on = fields.Datetime.now()
            int_picking.ongoing_order_id = response.get('in_order_id', '')
            int_picking.message_post(body=message)
        return True

    def _prepare_get_inbound_order_datas(self):
        """Prepare data to filter inbound orders
            @return - dictionary
        """
        today = fields.Datetime.now()
        date_from = self.env.company.last_inbound_sync
        return {
            #'date_from': date_from,
            'date_to': today,
        }

    @api.model
    def _cron_sync_inbound_order(self):
        companies = self.env['res.company'].search([('activate_ongoing', '=', True)], order='name desc')
        for company in companies:
            self = self.with_company(company)
            self._sync_inbound_order()


    ### return orders
    @api.model
    def _cron_get_return_order(self):
        companies = self.env['res.company'].search([('activate_ongoing', '=', True)], order='name desc')
        for company in companies:
            self = self.with_company(company)
            self._sync_return_order()


    @api.model
    def _sync_inbound_order(self):
        """
            This method will call from the schedule job, which is responsible to
            fetch data from the ongoing and validate the picking in odoo with
            received quantity
            @return - Bool
        """
        #TODO : check for which company we should take the credential (looping on company may be the solution ?)
        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            _logger.info('Ongoing: Credential Missing: Company :: {}'.format(self.env.company.name))
            return True
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        data = self._prepare_get_inbound_order_datas()
        try:
            response = request.get_inbound_order(data)
            if not response.get('success'):
                message = response.get('message', '')
                if response.get('error_message'):
                    message = message + '\n' + response['error_message']
                _logger.info('Ongoing: Failed to Sync Inbound order :: {}'.format(message))
                return True
            orders = self._prepare_data_from_response(response)
            self._process_inbound_picking(orders)
        except Exception as e:
            _logger.info('Ongoing: Failed to connect! :: {}'.format(str(e)))
        return True

    def _process_inbound_picking(self, orders):
        """
            This method will proccess the inbound transaction of ongoing in odoo
            @params : dict , response from the ongoing
            @return: bool
        """
        cr = self.env.cr
        Picking = self.env['stock.picking']
        backOrderModel = self.env['stock.backorder.confirmation']
        for k, v in orders.items():
            try:
                # Used to be: picking = Picking.search([('ongoing_order_id', '=', k), ('picking_type_code', '=', 'internal'), ('state', 'not in', ['cancel', 'done'])], limit=1)
                picking = Picking.search([('ongoing_order_id', '=', '%d' % k), ('picking_type_code', '=', 'incoming'),
                                          ('state', 'not in', ['cancel', 'done'])], limit=1)
                if not picking:
                    _logger.warning('No picking in correct state with ongoing_order %s', k)
                else:
                    #TODO :  should be handle batch/serial number
                    moves = picking.move_ids.filtered(lambda m: m.state not in ['cancel', 'done'] and m.product_id.tracking == 'none' and v.get(m.product_id.default_code))
                    if not moves:
                        _logger.warning('No moves in picking %s match the criteria', picking.name)
                    for move in moves:
                        rounding = move.product_id.uom_id.rounding
                        # TODO Used to be quantity_done
                        if float_compare(move.product_uom_qty, v.get(move.product_id.default_code), precision_rounding=rounding) == -1:
                            move.product_uom_qty = v.get(move.product_id.default_code)
                    if moves:
                        res = picking.with_context(skip_overprocessed_check=True).button_validate()
                        if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                            backorder_wizard = backOrderModel.with_context(res['context']).create({'pick_ids': [(4, picking.id)]})
                            backorder_wizard.process()
                    else:
                        _logger.warning('No moves to validate for picking %s', picking)
                    picking.company_id.last_inbound_sync = fields.Datetime.now()
                    #picking.ongoing_auto_validation()
                    cr.commit()
            except Exception as e:
                _logger.info('Ongoing: Failed to sync inbound order: {}'.format(str(e)))
                cr.rollback()
        return True

    def _prepare_data_from_response(self, response):
        data = {}
        for transaction in response['transactions']:
            key = transaction.InOrder.InOrderId
            if key not in data:
                data[key] = [{transaction.Article.ArticleNumber: float(transaction.NumberOfItems)}]
            else:
                data[key].append({transaction.Article.ArticleNumber: float(transaction.NumberOfItems)})
        orders = {}
        for k, v in data.items():
            orders[k] = dict(functools.reduce(operator.add, map(collections.Counter, data[k])))
        return orders

    # -----------------------
    # GET Out Order Transaction
    # -----------------------

    def _get_ongoing_pickings(self):
        return self.search([('ongoing_order_id', '!=', False),
                            ('sale_id', '!=', False),
                            ('picking_type_id.code', '=', 'outgoing'),
                            ('state', '=', 'assigned')])

    def _prepare_move_type(self, move_type):
        return (move_type, dict(self._fields['move_type'].selection).get(move_type))

    def _prepare_out_order_datas(self):
        internal_transfer = self.move_ids.move_dest_ids.mapped('picking_id')
        order_items = self.env['stock.move.line'].search([['picking_id', '=', self.id]])
        if not order_items:
            # last part is new
            order_items = self.move_ids_without_package.move_line_ids or self.move_ids_without_package


        data = {
            'sale_id' : self.sale_id,
            'picking_id' : self,
            'order_items': order_items,
            'reference': internal_transfer.name if internal_transfer and len(internal_transfer) == 1 else self.name,
            'in_date': self.scheduled_date or '',
            'move_type': self._prepare_move_type(self.move_type),
            'carrier': self.carrier_id and (self.carrier_id.transport_service_code, self.carrier_id.name)
        }
        return data

    def send_to_ongoing(self):
        pickings = self.search([('state', '=', 'assigned'),
                                ('sale_id', '!=', False),
                                ('picking_type_id.code', '=', 'outgoing'),
                                ('ongoing_order_id', '=', False)])
        _logger.info('Attempting to send these pickings to Ongoing: ')
        _logger.info(pickings)
        for record in pickings:
            _logger.info(record)
            cannot_send = False
            for line in record.move_ids:
                # TODO Verify this, used to be product_uom_qty != reserved_availability
                if line.product_uom_qty != line.quantity:
                    cannot_send = True
            if cannot_send:
                _logger.info('An ordered product is not in stock. Skipping this transfer - %s.', record.name)
            else:
                record.action_sync_so_order()

    def action_sync_so_order(self):
        if self.ongoing_order_id:
            _logger.info("Trying to ship order that's already shipped")
            raise ValidationError(_("Already shipped"))

        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            _logger.info('Ongoing: Credential Missing: Company :: {}'.format(self.env.company.name))
            return True
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        data = self._prepare_out_order_datas()
        try:
            response = request._prepare_process_order(data)
            _logger.debug(response)
            if not response.get('success'):
                message = response.get('message', '')
                if response.get('error_message'):
                    message = message + '\n' + response['error_message']
                _logger.info('Ongoing: Failed to Sync sale order :: {}'.format(message))
                return True
            self.last_sync_on = fields.Datetime.now()
            title = _('Synced with Ongoing WMS')
            message = Markup('<strong>{}</strong> <br/> <strong>Order ID :: </strong> {} <br/> <strong>Message ::</strong> {}'.format(title, response.get('order_id', ''), response.get('message', '')))
            self.ongoing_order_id = response.get('order_id', '')
            self.message_post(body=message)
        except Exception as e:
            _logger.info('Ongoing: Failed to connect! :: {}'.format(str(e)))
        return True

    def _set_tracking_number(self):
        """
        Retrieve tracking numbers for today's orders from Ongoing
        :return: None
        """

        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            _logger.info('Ongoing: Credential Missing: Company :: {}'.format(self.env.company.name))
            return True

        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        pickings = self._get_ongoing_pickings()
        ongoing_response = request._prepare_get_orders_by_query(pickings)

        try:
            ongoing_order_ids = [picking.ongoing_order_id for picking in self]
            if ongoing_order_ids and ongoing_response and ongoing_response.get('response'):
                response_dict = helpers.serialize_object(ongoing_response['response'], dict)
                picking_map = request.parse_tracking_numbers(response_dict)
                pickings._update_tracking_ref(picking_map)
                pickings._update_serial_number_line(picking_map)
        except Exception as e:
            _logger.info('Ongoing: Failed to connect! :: {}'.format(str(e)))
        return True

    def _cron_set_tracking_number(self):
        pickings = self._get_ongoing_pickings()
        _logger.info('Found these pickings')
        _logger.info(pickings)
        pickings._set_tracking_number()

    def action_set_tracking_number(self):
        if not self.ongoing_order_id:
            _logger.info("Trying to ship order that's not shipped")
            raise ValidationError(_("Not shipped"))
        self._set_tracking_number()
        title = _('Get Tracking Number')
        message = Markup('<strong>{}</strong> <br/> <strong>Tracking Number :: </strong> {}'.format(title, self.carrier_tracking_ref))
        self.message_post(body=message)

    def _cron_set_serial_number(self):
        company = self.company_id or self.env.company
        if not company.ongoing_sync_serial_numbers:
            return

        url, username, password, good_owner_code = self._get_ongoing_credential()
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        pickings = self._get_ongoing_pickings()
        serial_no_list = pickings._get_serial_numbers(request)
        picking_map = self._prepare_picking_map(serial_no_list)
        pickings._update_serial_number_line(picking_map)

    def action_set_serial_number(self):
        company = self.company_id or self.env.company
        if not company.ongoing_sync_serial_numbers:
            return

        url, username, password, good_owner_code = self._get_ongoing_credential()
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        if not self.ongoing_order_id:
            _logger.info("Trying to ship order that's not shipped")
            raise ValidationError(_("Not shipped"))
        serial_no_list = self._get_serial_numbers(request)
        picking_map = self._prepare_picking_map(serial_no_list)
        self._update_serial_number_line(picking_map)

    def _get_serial_numbers(self, request):
        res = {}
        for picking in self:
            response = request._get_serial_numbers_ongoing(int(picking.ongoing_order_id))
            if not response.get('success', False):
                _logger.info(f"Not Synced with Ongoing WMS For Ongoing_Order_id: {picking.ongoing_order_id} \n {response.get('message', ' ')}")
                continue
            if response.get('serial_no_list', False):
                res= {int(picking.ongoing_order_id): response.get('serial_no_list', False)}
        return res

    def _prepare_picking_map(self, serial_no_list):
        ongoing_order_dict = {ongoing_id:'Sendt' for ongoing_id, serialno in serial_no_list.items()}
        serial_no_dict = {ongoing_id:serialno for ongoing_id, serialno in serial_no_list.items()}
        return {'status': ongoing_order_dict, 'serial': serial_no_dict}

    def _update_tracking_ref(self, picking_map):
        for picking in self:
            order_id = int(picking.ongoing_order_id)
            tracking_id =  picking_map['status'].get(order_id) == 'Sendt' and \
                picking_map.get('tracking') and picking_map.get('tracking').get(order_id, False)
            if tracking_id:
                picking.carrier_tracking_ref = tracking_id

    def _update_serial_number_line(self, picking_map):
        for picking in self:
            if not picking.company_id.ongoing_sync_serial_numbers:
                continue

            order_id = int(picking.ongoing_order_id)
            if picking_map['status'].get(order_id) == 'Sendt':
                update_sr_qty_list = picking_map['serial'][order_id]
                product_code_list = tuple(map(lambda x:x.get('default_code'),  update_sr_qty_list))
                serial_no_list = tuple(map(lambda x:x.get('serial'), filter(lambda x:x.get('serial'), update_sr_qty_list)))
                serial_no_wo_list = list(filter(lambda x:not x.get('serial'), update_sr_qty_list))
                if serial_no_wo_list:
                    update_serial_list = picking._reduce_serial_number_list(serial_no_wo_list)
                    picking._process_without_serial_number_lines(update_serial_list)
                if serial_no_list:
                    picking._process_with_serial_number_lines(serial_no_list, product_code_list)

    def _process_without_serial_number_lines(self, serial_no_list):
        for product in serial_no_list:
            for move in self.move_ids_without_package.filtered(lambda line:line.state not in ['done', 'cancel']):
                if product and move.product_id.default_code == product.get('default_code'):
                    move.quantity_done = product.get('done_qty')
                    break

    def _process_with_serial_number_lines(self, serial_no_list, product_code_list):
        stock_lot_ids, unknown_serial_numbers= self._find_serial_numbers_in_lot(serial_no_list, product_code_list)
        if stock_lot_ids:
            for move in self.move_ids_without_package.filtered(lambda line: line.product_id.tracking == 'serial'):
                lines_to_create = []
                for lot in stock_lot_ids.filtered(lambda lot:move.product_id.default_code == lot.product_id.default_code \
                        and move.product_uom_qty != len(move.lot_ids.ids)):
                    lines_to_create.append((0, 0, {
                        'company_id': move.company_id.id,
                        'picking_id': move.picking_id.id,
                        'product_id': move.product_id.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'lot_id': lot.id,
                        'result_package_id': False,
                        'owner_id': False,
                        'qty_done': 1,
                        'product_uom_id': move.product_uom.id
                    }))
                    stock_lot_ids -= lot
                move.move_line_ids = lines_to_create
        if unknown_serial_numbers:
            self.message_post(body=Markup(f'List Of Serial Number {", ".join(unknown_serial_numbers)}<br /> Does Not Exist In Odoo.'),)

    def _find_serial_numbers_in_lot(self, serial_no_list, product_code_list):
        stock_lot = self.env['stock.lot']
        unknown_serial = []
        for serial in serial_no_list:
            if serial:
                lot_id = stock_lot.search([('name', '=', serial), ('company_id','=',self.env.company.id), ('product_id.default_code', 'in', product_code_list)], limit=1)
                stock_lot += lot_id
                if not lot_id:
                    unknown_serial.append(serial)
        return stock_lot, unknown_serial

    def _reduce_serial_number_list(self, serial_list):
        update_list = []
        product_code = []
        for serial in serial_list:
            if serial.get('default_code') not in product_code:
                update_list.append(serial.copy())
                product_code.append(serial.get('default_code'))
                continue
            for product_dict in update_list:
                if product_dict.get('default_code') == serial.get('default_code'):
                    product_dict.update({'done_qty': product_dict.get('done_qty') + serial.get('done_qty')})
                    break
        return update_list

    def _process_return_order(self, response):
        """ @see https://developer.ongoingwarehouse.com/get-return-orders-by-query """
        new_ids = []
        for info in response.GetReturnOrdersByQueryResult.ReturnOrders:
            order = {}
            order['return_code'] = info.ReturnCauseCode
            order['lines'] = [
                [ {
                    'product_id': article.OriginalArticleItemId,
                   'quantity': article.NumberOfItems
                   }
                    for article in line.ReturnedArticleItems
                ] for line in info.ReturnOrderLines
            ]

            new_ids.append(self.create(order))
        return new_ids


    def process_return_orders(self, orders):
        for order in orders['Order']:
            orderid = order['OrderInfo']['OrderId']
            picked = order['PickedOrderLines']
            if not picked:
                continue
            returns = [(x['Article'], x['ExternalOrderLineCode'], x['ReturnedNumberOfItems'])
                       for x in picked['PickedOrderLine']]
            # artikkel = SystemId Name ArticleNumber
            _logger.info('Returns for order %s is %s', orderid, returns)
            created_lines = []
            lines2process = []
            pickings = {}
            for ret in returns:
                if not ret[1] or ret[1]=='False':
                    _logger.error('No external order line code')
                    continue

                if ret[1] in created_lines:
                    _logger.error('More than one %d', ret[1])
                    continue

                line = self.env['stock.move'].search([('ongoing_line_number', '=', ret[1])])
                if not line:
                    raise ValidationError(_('Order line with ongoing number %s not found') % ret[1])
                if len(line) > 1:
                    raise ValidationError(_('More than one order line with ongoing numer %s found') % ret[1])

                picking = line.picking_id
                lines2process.append((line, ret[2]))
                if not picking in pickings:
                    pickings[picking] = []
                pickings[picking].append((ret[1], ret[2]))

            for picking, linez in pickings.items():
                retpicking = picking.copy()
                retpicking.ongoing_order_id = picking.ongoing_order_id
                _logger.info('Copy of picking %s is called %s', picking.name, retpicking.name)
                src = retpicking.location_id
                dst = retpicking.location_dest_id
                retpicking.location_id = dst  # Turn around
                retpicking.location_dest_id = src
                message = Markup(f'<strong>Created return move</strong> from picking {picking.name} for Ongoing order {picking.ongoing_order_id}')
                retpicking.message_post(body=message)
                linemap = dict([(x['ongoing_line_number'], x) for x in retpicking.move_ids])
                for (line_no, qty) in linez:
                    # line = self.env['stock.move'].search([('ongoing_line_number', '=', line_no)])
                    line = linemap[line_no]
                    line.quantity = qty
                    line.ongoing_line_number += '_r'
                    #line.message_post(body=message)

    def process_linez(self):

        for ret in lines2process:
            line = ret[0]
            created_lines.append(line.ongoing_line_number)
            qty = ret[1]
            retline = line.copy()
            if retline.ongoing_line_number:
                retline.ongoing_line_number += '_r'
            retline.quantity = qty
            src = retline.location_id
            dst = retline.location_dest_id
            retline.location_id = dst  # Turn around
            retline.location_dest_id = src
            message = Markup('<strong>Created return move</strong>')
            line.picking_id.message_post(body=message)

    def finn_sml(self):
        ###
        line = self.env['stock.move.line'].search([('ongoing_line_number', '=', ret[1])])
        if not line:
            raise ValidationError(_('Order line with ongoing number %s not found') % ret[1])
        retline = line.copy()
        retline.quantity = ret[2]
        src = retline.location_id
        dst = retline.location_dest_id
        retline.location_id = dst  # Turn around
        retline.location_dest_id = src
        message = Markup('<strong>Created return move</strong>')
        line.picking_id.message_post(body=message)

    @api.model
    def _sync_return_order(self):
        company = self.company_id or self.env.company
        if not company.activate_ongoing:
            return True

        url, username, password, good_owner_code = self._get_ongoing_credential()
        if not username or not password or not good_owner_code:
            raise UserError(_('Credential Missing'))
        request = OngoingRequest(self.log_xml, url, username, password, good_owner_code)
        ongoing_response = request._prepare_get_orders_by_query(last_sync=company.last_return_sync_on)
        if ongoing_response['response']:
            company.last_return_sync_on = fields.Datetime.now()
            self.process_return_orders(ongoing_response['response'])
        return True
