from odoo import models, api, fields, _
import random

class StockMoveLine(models.Model):
    _inherit = ['stock.move.line']

    ongoing_line_number = fields.Char('Line number', compute='_calc_line_number', store=True)

    def _calc_line_number(self):
        for ml in self:
            ml.ongoing_line_number = str(random.randrange(10000))