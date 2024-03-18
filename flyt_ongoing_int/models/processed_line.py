import logging
from odoo import models, api, fields, registry, SUPERUSER_ID, _

_logger = logging.getLogger(__name__)
class OngoingProcessedLine(models.Model):
    _name = 'ongoing_processed_line'
    _description = 'A line from Return order from Ongoing that has been processed.'

    _sql_constraints = [
        ('ongoing_processed_line_uniq', 'unique (picking_id, line_no)', "This Ongoing return has been processed already."),
    ]

    picking_id = fields.Many2one('stock.picking', 'Related picking')
    line_no = fields.Integer('Line number')
