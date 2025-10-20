{
    'name': 'Odoo WooCommerce Sync',
    'version': '1.0',
    'summary': 'Fetch WooCommerce orders and store to Sale Orders',
    'author': 'Jessy Ledama',
    'company': 'SIMI Technologies',
    'website': 'https://simitechnologies.co.ke',
    'license': 'LGPL-3',
    'category': 'Integration',
    'depends': ['base', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/woo_sync_views.xml',
        'data/woo_sync_cron.xml',
    ],
    'installable': True,
    'application': True,
}
