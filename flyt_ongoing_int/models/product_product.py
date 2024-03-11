from odoo import models, api, fields, _
import random

class Product(models.Model):
    _inherit = ['product.product']

    def _calc_short_display_name(self):
        for prod in self:
            dn = prod.display_name
            dc = prod.default_code
            pref = f'[{dc}]'
            if not dn.find(pref) == 0:
                continue # Non standard format or no code
            prod.short_display_name = dn[len(pref)+1:]

    short_display_name = fields.Char('Display name', compute='_calc_short_display_name')