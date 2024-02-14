# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import psycopg2
from odoo import models, api, fields, registry, SUPERUSER_ID, _
from odoo.exceptions import UserError
from .ongoing_wms_request import OngoingRequest

_logger = logging.getLogger(__name__)


class OngoingLoggerMixing(models.AbstractModel):
    _name = 'ongoing.logger.mixin'
    _description = 'Logger Mixin'

    last_sync_on = fields.Datetime(tracking=True)

    def _get_ongoing_credential(self):
        company = self.company_id or self.env.company
        username = company.ongoing_username
        password = company.ongoing_password
        good_owner_code = company.ongoing_good_owner_code
        
        return username, password, good_owner_code

    def log_xml(self, xml_string, func):
        self.flush()
        db_name = self._cr.dbname
        # Use a new cursor to avoid rollback that could be caused by an upper method
        try:
            db_registry = registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                IrLogging = env['ir.logging']
                IrLogging.sudo().create({
                    'name': 'ongoing.wms',
                    'type': 'server',
                    'dbname': db_name,
                    'level': 'DEBUG',
                    'message': xml_string,
                    'path': 'ongoing',
                    'func': func,
                    'line': 1
                })
        except psycopg2.Error:
            pass
