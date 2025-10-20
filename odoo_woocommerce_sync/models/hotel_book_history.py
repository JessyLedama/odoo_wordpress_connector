from odoo import models, fields

class HotelBookingHostory(models.Model):
    _inherit = "hotel.book.history"

    wp_booking_id = fields.Char(string="WordPress Booking ID")

