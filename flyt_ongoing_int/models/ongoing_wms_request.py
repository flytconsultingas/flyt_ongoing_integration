# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests

from datetime import datetime, date
from zeep import Client, Plugin, Settings
from zeep.exceptions import Fault
from zeep.wsdl.utils import etree_to_string

from odoo import _
from odoo.exceptions import ValidationError
from odoo.modules.module import get_resource_path
from odoo.tools import remove_accents
import random


_logger = logging.getLogger(__name__)

class LogPlugin(Plugin):
    """ Small plugin for zeep that catches out/ingoing XML requests and logs them"""
    def __init__(self, debug_logger):
        self.debug_logger = debug_logger

    def egress(self, envelope, http_headers, operation, binding_options):
        self.debug_logger(etree_to_string(envelope).decode(), 'ongoing_request')
        return envelope, http_headers

    def ingress(self, envelope, http_headers, operation):
        self.debug_logger(etree_to_string(envelope).decode(), 'ongoing_request')
        return envelope, http_headers

    def marshalled(self, context):
        context.envelope = context.envelope.prune()


class OngoingRequest():
    """ Low-level object intended to interface Odoo recordsets with Ongoing,
        through appropriate SOAP requests """

    def __init__(self, debug_logger, url, username, password, good_owner_code):
        self.debug_logger = debug_logger
        self.username = username
        self.password = password
        self.good_owner_code = good_owner_code

        if not url:
            raise ValidationError(_('Must configure API URL for Ongoing WMS'))


        self.client = Client(url)
        self.factory = self.client.type_factory("ns0")

    # --------------------------
        # Sync Products
    # --------------------------

    def _prepare_article_definition(self, data):
        ArticleDefinition = self.factory.ArticleDefinition()
        ArticleDefinition.ArticleNumber = data.get('default_code')
        ArticleDefinition.ArticleName = data.get('name')
        ArticleDefinition.BarCode = data.get('barcode')
        ArticleDefinition.PurchasePrice = data.get('price')
        ArticleDefinition.ArticleUnitCode = data.get('uom')

        ArticleOperation = self.factory.ArticleOperation('CreateOrUpdate')
        ArticleIdentificationType = self.factory.ArticleIdentificationType('ArticleNumber')
        ArticleDefinition.ArticleOperation = ArticleOperation
        ArticleDefinition.ArticleIdentification = ArticleIdentificationType
        if data.get('supplier'):
            ArticleDefinition.MainSupplier = self._prepare_supplier(
                data.get('supplier'))
        if data.get('alternate_suppliers'):
            ArticleDefinition.AlternativeSuppliers = self.factory.AlternativeSuppliers(self._prepare_suppliers(
                data.get('alternate_suppliers')))
        return ArticleDefinition

    def process_article(self, data):
        formatted_response = {
            'error_message': False,
            'goods_owner_order_number': False,
            'order_id': False,
            'in_order_id': False,
            'article_def_id': False,
            'success': False,
            'message': False,
        }
        try:
            self.response = self.client.service.ProcessArticle(
                GoodsOwnerCode=self.good_owner_code,
                UserName=self.username,
                Password=self.password,
                art=self._prepare_article_definition(data),
            )
            _logger.info(self.response)
            if 'ErrorMessage' in self.response:
                formatted_response['error_message'] = self.response.ErrorMessage
            if 'GoodsOwnerOrderNumber' in self.response:
                formatted_response['goods_owner_order_number'] = self.response.GoodsOwnerOrderNumber
            if 'OrderId' in self.response:
                formatted_response['order_id'] = self.response.OrderId
            if 'InOrderId' in self.response:
                formatted_response['in_order_id'] = self.response.InOrderId
            if 'ArticleDefId' in self.response:
                formatted_response['article_def_id'] = self.response.ArticleDefId
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if 'Message' in self.response:
                formatted_response['message'] = self.response.Message
        except Fault as fault:
            formatted_response['errors_message'] = fault
        except IOError:
            formatted_response['errors_message'] = "Ongoing Server Not Found"
        return formatted_response

    # --------------------------
        # Sync In Order
    # --------------------------

    def process_inorder(self, data):
        formatted_response = {
            'error_message': False,
            'goods_owner_order_number': False,
            'order_id': False,
            'in_order_id': False,
            'article_def_id': False,
            'success': False,
            'message': False,
        }
        try:
            self.response = self.client.service.ProcessInOrder(
                GoodsOwnerCode=self.good_owner_code,
                UserName=self.username,
                Password=self.password,
                co=self._prepare_inorder_defination(data),
            )
            _logger.info(self.response)
            if 'ErrorMessage' in self.response:
                formatted_response['error_message'] = self.response.ErrorMessage
            if 'GoodsOwnerOrderNumber' in self.response:
                formatted_response['goods_owner_order_number'] = self.response.GoodsOwnerOrderNumber
            if 'OrderId' in self.response:
                formatted_response['order_id'] = self.response.OrderId
            if 'InOrderId' in self.response:
                formatted_response['in_order_id'] = self.response.InOrderId
            if 'ArticleDefId' in self.response:
                formatted_response['article_def_id'] = self.response.ArticleDefId
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if 'Message' in self.response:
                formatted_response['message'] = self.response.Message
        except Fault as fault:
            formatted_response['errors_message'] = fault
        except IOError:
            formatted_response['errors_message'] = "Ongoing Server Not Found"
        return formatted_response

    def _prepare_orderinfo(self, data):
        InOrderInfo = self.factory.InOrderInfoClass()
        InOrderInfo.InOrderIdentification = 'GoodsOwnerOrderNumber'
        InOrderInfo.InOrderOperation = 'CreateOrUpdate'
        InOrderInfo.ReferenceNumber = data['reference']
        InOrderInfo.GoodsOwnerOrderNumber = data['order_number']
        InOrderInfo.OrderDate = data['order_date']
        InOrderInfo.InDate = data['in_date']
        return InOrderInfo

    def _prepare_inorder_customerinfo(self, data):
        InOrderCustomer = self.factory.InOrderCustomer()
        InOrderCustomer.InOrderCustomerIdentification = 'CustomerNumber'
        InOrderCustomer.InOrderCustomerOperation = 'CreateOrUpdate'
        InOrderCustomer.CustomerNumber = data['customer_number']
        InOrderCustomer.Name = data['customer_name']
        InOrderCustomer.Address = data['customer_address']
        InOrderCustomer.PostCode = data['customer_zip']
        InOrderCustomer.City = data['customer_city']
        InOrderCustomer.MobilePhone = data['customer_mobile']
        InOrderCustomer.TelePhone = data['customer_phone']
        InOrderCustomer.CountryCode = data['customer_country']
        return InOrderCustomer

    def _prepare_inorder_supplierinfo(self, data):
        InOrderSupplier = self.factory.InOrderSupplier()
        InOrderSupplier.InOrderSupplierIdentificationType = 'SupplierNumber'
        InOrderSupplier.InOrderSupplierOperation = 'Find'
        InOrderSupplier.SupplierNumber = data['supplier_number']
        #InOrderSupplier.SupplierName = ''

        return InOrderSupplier

    def _prepare_inorder_orderlineinfo(self, data):
        InOrderLines = self.factory.ArrayOfInOrderLine()
        lines = []
        for line in data['lines']:
            InOrderLine = self.factory.InOrderLine()
            InOrderLine.OrderLineIdentification = 'ArticleNumber'
            InOrderLine.ArticleIdentification = 'ArticleNumber'
            InOrderLine.NumberOfItems = line['quantity']
            InOrderLine.ArticleNumber = line['product_code']
            lines.append(InOrderLine)
        InOrderLines.InOrderLine = lines
        return InOrderLines

    def _prepare_inorder_defination(self, data):
        InOrderInfo = self._prepare_orderinfo(data)
        #InOrderCustomer = self._prepare_inorder_customerinfo(data)
        InOrderLines = self._prepare_inorder_orderlineinfo(data)

        InOrder = self.factory.InOrder()
        InOrder.InOrderLines = InOrderLines
        #InOrder.InOrderCustomer = InOrderCustomer
        InOrder.InOrderSupplier = self._prepare_inorder_supplierinfo(data)
        InOrder.InOrderInfo = InOrderInfo
        return InOrder

    # -----------------------
    # GET InOrder Transaction
    # -----------------------

    def get_inbound_order(self, data):
        formatted_response = {
            'error_message': False,
            'goods_owner_order_number': False,
            'order_id': False,
            'in_order_id': False,
            'article_def_id': False,
            'success': False,
            'message': False,
            'transactions': list()
        }
        try:
            self.response = self.client.service.GetInboundTransactionsByQuery(
                GoodsOwnerCode=self.good_owner_code,
                UserName=self.username,
                Password=self.password,
                Query=self._prepare_inbound_query(data),
            )
            _logger.info(self.response)
            if 'ErrorMessage' in self.response:
                formatted_response['error_message'] = self.response.ErrorMessage
            if 'GoodsOwnerOrderNumber' in self.response:
                formatted_response['goods_owner_order_number'] = self.response.GoodsOwnerOrderNumber
            if 'OrderId' in self.response:
                formatted_response['order_id'] = self.response.OrderId
            if 'InOrderId' in self.response:
                formatted_response['in_order_id'] = self.response.InOrderId
            if 'ArticleDefId' in self.response:
                formatted_response['article_def_id'] = self.response.ArticleDefId
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if 'Message' in self.response:
                formatted_response['message'] = self.response.Message
            if 'InboundTransactions' in self.response:
                formatted_response['transactions'] = self.response.InboundTransactions and \
                    self.response.InboundTransactions.GoodsOwnerInboundTransaction or []
        except Fault as fault:
            formatted_response['errors_message'] = fault
        except IOError:
            formatted_response['errors_message'] = "Ongoing Server Not Found"
        return formatted_response
    
    def _prepare_inbound_query(self, data):
        Query = self.factory.GetGoodsOwnerInboundTransactionsQuery()
        if data.get('date_from'):
            Query.InDateFrom = data['date_from']
        #Query.InDateTo = data['date_to']
        Query.InboundTransactionTypesToGet = 'ReceivedOnInOrder'
        return Query

    # ----------------------------------
    # For creating Sale Order in ongoing
    # ----------------------------------

    def _prepare_order_info(self, data):
        sale_id = data['sale_id']
        picking_id = data['picking_id'].name
        OrderInfoClass = self.factory.OrderInfoClass()
        OrderInfoClass.OrderIdentification = 'GoodsOwnerOrderNumber'
        OrderInfoClass.OrderOperation = 'CreateOrUpdate'
        OrderInfoClass.GoodsOwnerOrderNumber = f'{sale_id.id}-{picking_id.split("/")[2]}'
        OrderInfoClass.DeliveryInstruction = sale_id.client_order_ref
        OrderInfoClass.DeliveryDate = data['in_date']
        OrderInfoClass.ConsigneeOrderNumber = sale_id.client_order_ref

        OrderInfoClass.WayOfDeliveryType = self._prepare_way_of_delivery_type(data)
        OrderInfoClass.TermsOfDeliveryType = self._prepare_terms_of_delivery_type()
        return OrderInfoClass

    def _prepare_way_of_delivery_type(self, data):
        # used to be move_type, but now is (transport_service_code, name)
        # Maybe use data['carrier'] to use picking carrier
        way = (data['sale_id'].carrier_id.transport_service_code,
               data['sale_id'].carrier_id.name)
        WayOfDeliveryType = self.factory.WayOfDeliveryType()
        WayOfDeliveryType.WayOfDeliveryTypeOperation = "CreateOrUpdate"
        WayOfDeliveryType.WayOfDeliveryTypeIdentification = "Code"
        WayOfDeliveryType.Code = way[0]
        WayOfDeliveryType.Name = way[1]
        return WayOfDeliveryType

    def _prepare_terms_of_delivery_type(self):
        TypeClass = self.factory.TypeClass()
        TypeClass.TypeOperation = "Find"
        TypeClass.TypeIdentification = "Name"
        TypeClass.Name = "Standard"
        return TypeClass

    def _create_shipping_address(self, partner, sale_id):
        has_parent = False
        parent = None
        order = sale_id

        if not hasattr(order, "flyt_so_ordered_by_contact") or (order.company_id and order.company_id.ongoing_use_shipping_name):
            recipient_name = partner.name
        else:
            if order.flyt_so_ordered_by_contact.parent_id:
                has_parent = True
                parent = order.flyt_so_ordered_by_contact.parent_id

            recipient_name = (order.flyt_so_ordered_by_contact.name if
                              order.flyt_so_ordered_by_contact.name else
                              partner.parent_id.name if partner.parent_id else partner.name)

        if not (order.company_id and order.company_id.ongoing_use_shipping_name):
            recipient_name = partner.parent_id.name if partner.parent_id else recipient_name

        if has_parent:
            recipient_name = parent.name

        if hasattr(order, 'flyt_so_shipping_street'):
            recipient_address = (order.flyt_so_shipping_street if
                                 order.flyt_so_shipping_street else (partner.street if
                                                                          partner.street else " "))
        else:
            recipient_address = partner.street if partner.street else " "

        if hasattr(order, 'flyt_so_shipping_co_or_company_name'):
            recipient_address2 = ("c/o " + order.flyt_so_shipping_co_or_company_name if
                                  order.flyt_so_shipping_co_or_company_name else ("c/o " + partner.street2
                                                                                       if partner.street2 else " "))
        else:
            recipient_address2 = (partner.street2 if
                                  partner.street2 else " ")

        if hasattr(order, 'flyt_so_shipping_postal_code'):
            recipient_postal_code = (order.flyt_so_shipping_postal_code if
                                     order.flyt_so_shipping_postal_code else partner.zip)
        else:
            recipient_postal_code = partner.zip

        if hasattr(order, 'flyt_so_shipping_city'):
            recipient_city = (order.flyt_so_shipping_city if
                              order.flyt_so_shipping_city else partner.city)
        else:
            recipient_city = partner.city

        recipient_country_code = (partner.country_id.code if
                                  partner.country_id.code else "no")

        recipient_reference = sale_id.flyt_so_reservation[
                              :35] if sale_id.flyt_so_reservation else ''

        # Use recipient name as contact name if recipient has parent
        address3 = "Att: " + partner.name if partner.parent_id else None

        address = {
            "name": recipient_name,
            "address": recipient_address,
            "address2": recipient_address2,
            "zipcode": recipient_postal_code,
            "city": recipient_city,
            "country_code": recipient_country_code,
            "reference": recipient_reference,
            "address3": address3
        }
        return address

    def _prepare_customer(self, data):
        partner = data['sale_id'].partner_shipping_id
        shipping_address = self._create_shipping_address(partner, data['sale_id'])
        Customer = self.factory.Customer()
        customer_number = str(partner.id)
        name = shipping_address["name"]
        street = shipping_address["address"]
        address2 = shipping_address["address2"]
        address3 = shipping_address["address3"]
        zipcode = str(shipping_address["zipcode"])
        city = shipping_address["city"]
        phone = partner.phone or ''
        remark = data['sale_id'].client_order_ref
        email = partner.email
        mobile = partner.mobile or ''
        country_code = shipping_address["country_code"]

        Customer.CustomerOperation = "CreateOrUpdate"
        Customer.CustomerIdentification = "ExternalCustomerCode"
        Customer.ExternalCustomerCode = customer_number
        Customer.CustomerNumber = partner.ref or ''
        Customer.Name = name
        Customer.Address = street
        Customer.Address2 = address2
        Customer.Address3 = address3
        Customer.PostCode = zipcode
        Customer.City = city
        Customer.Telephone = phone
        Customer.Remark = remark
        Customer.Email = email
        Customer.MobilePhone = str(mobile)
        Customer.CountryCode = country_code if country_code else "NO"
        Customer.NotifyBySMS = "true" if mobile else "false"
        Customer.NotifyByEmail = "true" if email else "false"
        Customer.NotifyByTelephone = "true" if email else "false"
        Customer.IsVisible = "false"
        return Customer


    def _prepare_supplier(self, data):
        #partner = data['sale_id'].partner_shipping_id
        #shipping_address = self._create_shipping_address(partner, data['sale_id'])
        Supplier = self.factory.Supplier()
        supplier_number = data['partner_id']

        #remark = data['sale_id'].client_order_ref
        email = data['email']
        mobile = data['mobile']
        country_code = data["country_code"]

        Supplier.SupplierOperation = "CreateOrUpdate"
        Supplier.SupplierIdentificationType = "SupplierNumber"
        Supplier.SupplierNumber = supplier_number
        Supplier.SupplierName = data['name']
        Address = self.factory.AddressClass()
        Address.Address = data['street']
        Address.Address2 = data['street2']
        #Supplier.Address3 = address3
        Address.PostCode = data['zip']
        Address.City = data['city']
        Address.Telephone = data['phone']
        Address.Remark = data['remark']
        Address.Email = email
        Address.MobilePhone = data['mobile']
        Address.CountryCode = country_code if country_code else "NO"
        Address.NotifyBySMS = "true" if mobile else "false"
        Address.NotifyByEmail = "true" if email else "false"
        Address.NotifyByTelephone = "true" if email else "false"
        Address.IsVisible = "false"
        Supplier.Address = Address
        return Supplier

    def _prepare_suppliers(self, data):
        return [self.factory.AlternativeSupplier(self._prepare_supplier(supp)) for supp in data]

    def _prepare_transporter_contract(self, data):
        _logger.info("Preparing the transporter contract")
        _logger.info("Transporter Service Code is %s", data['sale_id'].carrier_id.fh_transport_service_code)

        TransporterContractClass = self.factory.TransporterContractClass()
        TransporterContractClass.TransporterContractIdentification = "ServiceCode"
        TransporterContractClass.TransporterContractOperation = "Find"
        TransporterContractClass.TransportPayment = "Prepaid"
        TransporterContractClass.TransporterServiceCode = data['sale_id'].carrier_id.transport_service_code
        return TransporterContractClass

    def _get_line_qty(self, line):
        if hasattr(line, 'quantity_product_uom'):
            return getattr(line, 'quantity_product_uom', None)
        else:
            return getattr(line, 'product_uom_qty')

    def _prepare_customer_order_lines(self, data):
        ArrayOfCustomerOrderLine = self.factory.ArrayOfCustomerOrderLine()
        order_items = data['order_items']
        CustomerOrderLine = []

        lines = {}
        for line in order_items:
            if not line.ongoing_line_number:
                ongoing_line_number = random.randrange(1000)
                line.update({'ongoing_line_number': ongoing_line_number})
                picking = (line.picking_id and line.picking_id.name) or line.picking_id
                _logger.debug('%s Writing line number %s for line id %s - picking %s', line, ongoing_line_number, line.id, picking)
            else:
                ongoing_line_number = line.ongoing_line_number
            key = line.product_id.id
            if key not in lines:
                lines[key] = {
                    'quantity': self._get_line_qty(line),
                    'default_code': line.product_id.default_code,
                    'line_number': ongoing_line_number,
                }
            else:
                lines[key]['quantity'] += self._get_line_qty(line)

        _logger.debug('prepare_customer_order_lines %s', ','.join(['%s' % x['line_number'] for x in lines.values()]))

        for order_item in lines.values():
            CustomerOrderLine.append(self._prepare_customer_orderline(order_item))
        ArrayOfCustomerOrderLine.CustomerOrderLine = CustomerOrderLine
        return ArrayOfCustomerOrderLine

    def _prepare_customer_orderline(self, order_line):
        CustomerOrderLine = self.factory.CustomerOrderLine()
        CustomerOrderLine.VatCode = self._prepare_vat_code()
        CustomerOrderLine.OrderLineIdentification = "ArticleNumber"
        CustomerOrderLine.ArticleIdentification = "ArticleNumber"
        CustomerOrderLine.ArticleNumber = order_line['default_code']
        CustomerOrderLine.NumberOfItems = str(order_line['quantity'])
        CustomerOrderLine.ExternalOrderLineCode = str(order_line['line_number'])
        return CustomerOrderLine

    def _prepare_vat_code(self):
        VatCode = self.factory.VatCodeClass()
        VatCode.VatCodeOperation = "Find"
        VatCode.VatCodeIdentification = "VatPercent"
        VatCode.VatPercent = "25"
        return VatCode

    def _prepare_process_order(self, data):
        formatted_response = {
            'error_message': False,
            'goods_owner_order_number': False,
            'order_id': False,
            'in_order_id': False,
            'article_def_id': False,
            'success': False,
            'message': False,
        }
        try:
            self.response = self.client.service.ProcessOrder(
                GoodsOwnerCode=self.good_owner_code,
                UserName=self.username,
                Password=self.password,
                co=self._prepare_customer_order(data),
            )
            _logger.info(self.response)
            if 'ErrorMessage' in self.response:
                formatted_response['error_message'] = self.response.ErrorMessage
            if 'GoodsOwnerOrderNumber' in self.response:
                formatted_response['goods_owner_order_number'] = self.response.GoodsOwnerOrderNumber
            if 'OrderId' in self.response:
                formatted_response['order_id'] = self.response.OrderId
            if 'InOrderId' in self.response:
                formatted_response['in_order_id'] = self.response.InOrderId
            if 'ArticleDefId' in self.response:
                formatted_response['article_def_id'] = self.response.ArticleDefId
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if 'Message' in self.response:
                formatted_response['message'] = self.response.Message
        except Fault as fault:
            formatted_response['errors_message'] = fault
            raise fault
        except IOError as error:
            formatted_response['errors_message'] = "Ongoing Server Not Found"
            raise error
        return formatted_response

    def _prepare_customer_order(self, data):
        _logger.info(data or '')
        CustomerOrder = self.factory.CustomerOrder()
        CustomerOrder.OrderInfo = self._prepare_order_info(data)
        CustomerOrder.Customer = self._prepare_customer(data)
        CustomerOrder.TransporterContract = self._prepare_transporter_contract(data)
        CustomerOrder.CustomerOrderLines = self._prepare_customer_order_lines(data)
        _logger.debug('prepare_customer_order %s', CustomerOrder)
        return CustomerOrder

    def _prepare_get_orders_by_query(self, data=None, last_sync=None):
        formatted_response = {
            'error_message': False,
            'goods_owner_order_number': False,
            'order_id': False,
            'in_order_id': False,
            'article_def_id': False,
            'response': False,
            'success': False,
            'message': False,
        }
        try:
            self.response = self.client.service.GetOrdersByQuery(
                GoodsOwnerCode=self.good_owner_code,
                UserName=self.username,
                Password=self.password,
                query=self._prepare_orders(data, last_sync),
            )
            _logger.info(self.response)
            formatted_response['response'] = self.response
            if not self.response:
                return formatted_response

            if 'ErrorMessage' in self.response:
                formatted_response['error_message'] = self.response.ErrorMessage
            if 'GoodsOwnerOrderNumber' in self.response:
                formatted_response['goods_owner_order_number'] = self.response.GoodsOwnerOrderNumber
            if 'OrderId' in self.response:
                formatted_response['order_id'] = self.response.OrderId
            if 'InOrderId' in self.response:
                formatted_response['in_order_id'] = self.response.InOrderId
            if 'ArticleDefId' in self.response:
                formatted_response['article_def_id'] = self.response.ArticleDefId
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if 'Message' in self.response:
                formatted_response['message'] = self.response.Message
        except Fault as fault:
            formatted_response['errors_message'] = fault
        except IOError:
            formatted_response['errors_message'] = "Ongoing Server Not Found"

        return formatted_response

    def parse_tracking_numbers(self, response):
        Orders = response.get('Order')
        picking_map = {"status": {}, "tracking": {}, "tracking_url": {}, "serial": {}}

        for Order in Orders:
            OrderInfo = Order['OrderInfo']
            OrderPalletItems = Order['OrderPalletItems']

            # Obtain order status
            order_id = OrderInfo['OrderId']
            order_status = OrderInfo['OrderStatusText']
            picking_map['status'][order_id] = order_status

            # Obtain tracking number
            if order_status == "Sendt" and OrderPalletItems:
                for pallet_item in OrderPalletItems['OrderPalletItemInfo']:
                    if not pallet_item['IsTaPalletItem']:
                        continue
                    tracking_number = pallet_item['LabelId'] or ''
                    tracking_url = pallet_item.get('Tracking', None) and pallet_item['Tracking']['TrackingUrl']
                    picking_map['tracking'][order_id] = tracking_number
                    if order_id not in picking_map['tracking_url']:
                        picking_map['tracking_url'][order_id] = []
                    picking_map['tracking_url'][order_id].append(tracking_url)

            # Obtain serials
            if order_status == "Sendt" and Order['PickedArticleItems']:
                serial = [({'default_code': res['Article']['ArticleNumber'], 'serial':res['Serial'], 'done_qty': int(res['NumberOfItems'])}) for res in Order['PickedArticleItems']['PickedArticleItem']]
                picking_map['serial'][order_id] = serial

        return picking_map

    def _prepare_orderids(self, pickings):
        ongoing_order_ids = [picking.ongoing_order_id for picking in pickings]
        ArrayOfInt = self.factory.ArrayOfInt()
        int = []
        for ongoing_order_id in ongoing_order_ids:
            int.append(ongoing_order_id)

        ArrayOfInt.int = int
        return ArrayOfInt

    def _prepare_orders(self, pickings, last_sync=None):
        OrderFilters = self.factory.OrderFilters()

        if pickings:
            OrderFilters.OrderIdsToGet = self._prepare_orderids(pickings)

        if last_sync:
            OrderFilters.LastReturnedFrom = last_sync

        return OrderFilters

    def _get_serial_numbers_ongoing(self, order_id):
        formatted_response = {
            'success': False,
            'message': False,
            'serial_no_list': False,
        }
        try:
            self.response = self.client.service.GetOrder(
                UserName=self.username,
                Password=self.password,
                OrderId=order_id,
            )
            _logger.info(self.response)
            if 'Success' in self.response:
                formatted_response['success'] = self.response.Success
            if formatted_response['success'] and self.response['PickedArticleItems']:
                formatted_response['serial_no_list'] = [({'default_code': res['Article']['ArticleNumber'], 'serial':res['Serial'], 'done_qty': int(res['NumberOfItems'])})for res in self.response['PickedArticleItems']['PickedArticleItem']]
        except Fault as fault:
            formatted_response['message'] = fault
        except IOError:
            formatted_response['message'] = "Ongoing Server Not Found"
        return formatted_response

    def get_return_orders_ongoing(self):
        formatted_response = {
            'success': False,
            'message': False,
            'serial_no_list': False,
        }
        try:
            self.response = self.client.service.GetOrdersByQuery(
                UserName=self.username,
                Password=self.password,
                GoodsOwnerCode='Lillelam, Odoo',
                GetOrdersQuery=self._prepare_get_orders_by_query(),
            )
            _logger.info(self.response)
            assert not self.response['ReturnOrders']

        except IOError:
            formatted_response['message'] = "Ongoing Server Not Found"

        if 'Success' in self.response:
            formatted_response['success'] = self.response.Success

        return formatted_response