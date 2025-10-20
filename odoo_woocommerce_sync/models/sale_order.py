
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_woo_synced = fields.Boolean(string="Synced to Woo", default=False)
    is_woo_imported = fields.Boolean(string="Imported from Woo", default=False)
