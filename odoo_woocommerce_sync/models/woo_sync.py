from odoo import models, fields
import requests
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class WooSync(models.Model):
    _name = "woo.sync"
    _description = "WooCommerce Synchronization"

    name = fields.Char(string="Description", default="WooCommerce Sync")

    last_sync_status = fields.Text(string="Last Sync Log")

    last_sync_date = fields.Datetime(string="Last Sync Date")

    consumer_key = fields.Char(string="Consumer Key")

    consumer_secret = fields.Char(string="Consumer Secret")

    url = fields.Char(string="URL")

    def action_fetch_orders(self):
        if not self.consumer_key or not self.consumer_secret or not self.url:
            msg = "Missing WooCommerce API credentials!"
            _logger.warning(msg)
            self.last_sync_status = msg
            return
        
        url = self.url
        params = {
            "consumer_key": self.consumer_key,
            "consumer_secret": self.consumer_secret,
        }

        # Fetch orders updated since last sync

        last_sync_date = self.last_sync_date or (fields.Datetime.now() - timedelta(days=7))
        
        params['after'] = last_sync_date.isoformat()

        try:
            all_orders = []

            page = 1

            while True:
                params.update({'page': page,
                               'per_page': 100,
                               'orderby': 'date',
                                'order': 'desc',
                               })
                
                response = requests.get(url, params=params, timeout=30)

                if response.status_code != 200:
                    msg = f"❌ WooCommerce HTTP Error: {response.status_code}"
                    
                    _logger.warning(msg)

                    self.write({'last_sync_status': msg})
                    
                    return
                
                orders = response.json()

                if not orders:
                    break

                all_orders.extend(orders)

                page += 1

            created = 0

            for order in all_orders:
                woo_id = order.get('id')
                email = order.get('billing', {}).get('email')
                customer_name = "%s %s" % (
                    order.get('billing', {}).get('first_name', ''),
                    order.get('billing', {}).get('last_name', '')
                )

                # Find or create customer
                partner = self.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
                if not partner:
                    partner = self.env['res.partner'].sudo().create({
                        'name': customer_name.strip() or f"Woo Customer {woo_id}",
                        'email': email or f"woo_{woo_id}@example.com",
                        'phone': order.get('billing', {}).get('phone', ''),
                    })

                # Skip if already imported
                existing_order = self.env['sale.order'].sudo().search([('client_order_ref', '=', str(woo_id))], limit=1)
                if existing_order:
                    continue

                # Handle date safely
                date_str = order.get('date_created')
                try:
                    date_created = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else fields.Datetime.now()
                except Exception:
                    date_created = fields.Datetime.now()

                # prepare booking details
                booking_created = False

                # Create corresponding Hotel Booking record
                if not booking_created:
                    # Try to extract check-in and check-out info from metadata
                    check_in = None
                    check_out = None
                    for meta in order.get('meta_data', []):
                        key = meta.get('key', '').lower()
                        if 'checkin' in key or 'check_in' in key:
                            check_in = meta.get('value')
                        elif 'checkout' in key or 'check_out' in key:
                            check_out = meta.get('value')

                    # fallback defaults if missing
                    check_in = check_in or date_created
                    check_out = check_out or fields.Datetime.add(date_created, days=1)

                    self.env['hotel.book.history'].create({
                        'room_id': product.id,      # product matched by name
                        'partner_id': partner.id,   # customer
                        'check_in': check_in,
                        'check_out': check_out,
                    })
                    booking_created = True  # avoid duplicate bookings per order

                # Prepare order lines
                order_lines = []
                for item in order.get('line_items', []):
                    product_name = item.get('name', 'Unknown')
                    sku = item.get('sku')
                    price = float(item.get('price', 0.0))
                    qty = float(item.get('quantity', 1))

                    product = self.env['product.product'].sudo().search([
                        '|', ('name', '=', product_name),
                        ('default_code', '=', sku)
                    ], limit=1)

                    if not product:
                        product = self.env['product.product'].sudo().create({
                            'name': product_name,
                            'list_price': price,
                            'default_code': sku or f"WOO-{item.get('id')}",
                        })

                    order_lines.append((0, 0, {
                        'product_id': product.id,
                        'product_uom_qty': qty,
                        'price_unit': price,
                        'name': product_name,
                    }))

                # create reservation
                self.env['hotel.booking.history'].sudo().create({
                    'room_id': product.id,
                    'partner_id': partner.id,
                    'check_in': check_in,
                    'check_out': check_out,
                })

                _logger.info(f"Created booking for order {woo_id} for partner {partner.name}")

                # Create sale order
                self.env['sale.order'].sudo().create({
                    'partner_id': partner.id,
                    'client_order_ref': str(woo_id),
                    'date_order': date_created,
                    'origin': 'WooCommerce',
                    'order_line': order_lines,
                })

                created += 1

            msg = f"✅ WooCommerce Sync Complete: {created} new orders imported."
            _logger.warning(msg)
            self.write({'last_sync_status': msg})
            self.write({'last_sync_date': fields.Datetime.now()})

        except Exception as e:
            msg = f"❌ WooCommerce Sync Error: {e}"
            _logger.warning(msg)
            self.write({'last_sync_status': msg})

    def action_post_order_to_woo(self):
        if not self.consumer_key or not self.consumer_secret or not self.url:
            msg = "Missing WooCommerce API credentials!"
            _logger.warning(msg)
            self.last_sync_status = msg
            return

        saleOrder = self.env['sale.order']

        orders = saleOrder.search(
            [
                ("is_woo_imported", "=", False), 
                ("is_woo_synced", "=", False),
                ("state", "=", "sale")
            ])
        
        if not orders:
            msg = "No new Odoo-originated orders to sync."
            _logger.info(msg)
            self.last_sync_status = msg
            return
        
        posted = 0

        for sale_order in orders:
        
            url = self.url
            params = {
                "consumer_key": self.consumer_key,
                "consumer_secret": self.consumer_secret,
            }

            data = {
                "payment_method": "bacs",
                "payment_method_title": "Direct Bank Transfer",
                "set_paid": True,
                "billing": {
                    "first_name": sale_order.partner_id.name,
                    "email": sale_order.partner_id.email,
                    "phone": sale_order.partner_id.phone,
                },
                "line_items": [
                    {
                        "product_id": line.product_id.id,  # WooCommerce product ID
                        "quantity": int(line.product_uom_qty),
                    } for line in sale_order.order_line
                ]
            }

            try:
                response = requests.post(url, params=params, json=data, timeout=30)
                if response.status_code in [200, 201]:
                    _logger.info("WooCommerce Order posted successfully: %s", response.json())
                else:
                    _logger.warning("WooCommerce POST failed [%s]: %s", response.status_code, response.text)
            except Exception as e:
                _logger.error("Error posting order to WooCommerce: %s", e)
        
        msg = f"✅ WooCommerce Sync Complete: {posted} Odoo orders posted to Woo."
        _logger.info(msg)
        self.last_sync_status = msg

