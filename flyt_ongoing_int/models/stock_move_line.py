from odoo import models, api, fields, _
import random

class StockMoveLine(models.Model):
    _inherit = ['stock.move.line']

    ongoing_line_number = fields.Char('Line number', tracking=True)
