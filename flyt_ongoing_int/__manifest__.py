# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Ongoing WMS Connector",

    'summary': """
        Ongoing WMS Connector""",

    'description': """
        Ongoing WMS Connector
        Task: 3270372, 3461081, 3525703, 3678664
    """,

    'author': "Odoo PS",
    'website': "https://www.odoo.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Customisation',
    'version': '17.0.0.0.7',

    # any module necessary for this one to work correctly
    'depends': ['purchase_stock', 'sale_stock', 'delivery'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/purchase_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/res_config_settings_views.xml',
        'views/delivery_view.xml',
        'data/cron.xml',
    ],
    'license': 'OEEL-1',
    # only loaded in demonstration mode
}
