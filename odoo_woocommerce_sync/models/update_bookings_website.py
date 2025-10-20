from odoo import models, fields, api
import requests
import logging
from datetime import datetime, timedelta
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class UpdateBookings(models.Model):
    _name = "update.bookings"
    _description = "Update Bookings in Website"


    name = fields.Char(string="Name")

    status = fields.Char(string="Status")

    wp_room_id = fields.Char(string="WordPress Room ID")

    room_name = fields.Char(string="Room Name")

    checkin_date = fields.Datetime(string="Checkin Date")

    checkout_date = fields.Datetime(string="Checkout Date")

    consumer_key = fields.Char(string="Consumer Key")

    consumer_secret = fields.Char(string="Consumer Secret")

    url = fields.Char(string="URL")

    wp_booking_id = fields.Char(string="WordPress Booking ID")

    last_sync_date = fields.Datetime(string="Last Sync Date")

    last_sync_status = fields.Char(string="Last Sync Status")

    
    def update_bookings(self):
        """
        This method is triggered from the button in the form/view.
        It fetches all bookings without wp_booking_id, sends them to WordPress,
        and updates the wp_booking_id field.
        """
        # Fetch bookings in the system (replace with your actual booking model)
        bookings_to_sync = self.env['hotel.book.history'].search([('wp_booking_id', '=', False)])

        if not bookings_to_sync:
            raise UserError("No new bookings to send.")
        
        url = self.url

        for booking in bookings_to_sync:
            if booking.wp_booking_id:
                # data already sent to website
                continue

            payload = {
                "title": booking.name or f"Booking for {booking.room_name}",
                "checkin": str(booking.checkin_date),
                "checkout": str(booking.checkout_date),
                "status": booking.status,
            }

            wp_room_id = booking.wp_room_id

            if not wp_room_id and booking.room_name:
                try:
                    resp = requests.get(
                        f"https://blueberryvillas.co.ke/wp-json/wp/v2/loftocean_room",
                        params={"search": booking.room_name},
                        timeout=10
                    )

                    if resp.status_code == 200:
                        rooms = resp.json()
                        if rooms:
                            wp_room_id = rooms[0]["id"]
                            booking.wp_room_id = wp_room_id  # save for future use
                except Exception as e:
                    _logger.error(f"Error fetching WP room ID for '{booking.room_name}': {e}")


            # send either room_id or room_name
            if wp_room_id:

                payload["room_id"] = wp_room_id
            
            elif booking.room_name:
                
                payload["room_name"] = booking.room_name
            
            else:
                raise UserError("Please set either a WordPress Room ID or Room Name.")

            try:
                
                response = requests.post(url, json=payload, timeout=15)
            
            except Exception as e:
                
                _logger.error(f"Error sending booking {booking.name}: {e}")
                booking.last_sync_status = f"Error: {e}"
                continue

            if response.status_code != 200:
                
                _logger.error(f"WordPress API error for booking {booking.name}: {response.text}")
                booking.last_sync_status = f"WP API error: {response.status_code}"
                continue

            data = response.json()
            wp_id = data.get("id")
            if wp_id:
                booking.wp_booking_id = wp_id
                booking.last_sync_date = fields.Datetime.now()
                booking.last_sync_status = "Sent successfully"
            else:
                booking.last_sync_status = f"No ID returned from WP"

        return True


