from odoo import models, api, fields, _
import random

class StockMove(models.Model):
    _inherit = ['stock.move']

    ongoing_line_number = fields.Char('Line number', tracking=True)