# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
import datetime
import logging
import requests
import os

_logger = logging.getLogger(__name__)


# Helper function to get API configuration
def _get_api_config():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../.env')
    api_key = None
    try:
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("BDL_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
                    break
    except Exception as e:
        _logger.error("Could not read .env file: %s", e)
    return {'api_key': api_key}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_pos_created = fields.Boolean(string='Create from POS')

    @api.model
    def craete_saleorder_from_pos(self, oderdetails):
        vals = {}
        saleorder_id = self.env['sale.order'].create({
            'partner_id': oderdetails.get('partner_id'),
            'date_order': datetime.date.today(),
            'is_pos_created': True,
            'state': 'draft',
            'amount_tax': oderdetails.get('tax_amount'),
            })
        vals['name'] = saleorder_id.name
        vals['id'] = saleorder_id.id
        for data in oderdetails:
            if not data == 'partner_id' and not data == 'tax_amount':
                current_dict = oderdetails.get(data)
                saleorder_id.order_line = [(0, 0, {
                    'product_id': current_dict.get('product'),
                    'product_uom_qty':  current_dict.get('quantity'),
                    'price_unit': current_dict.get('price'),
                    'discount': current_dict.get('discount'),
                })]
        return vals

    def action_confirm_and_create_stock_order(self):
        """
        Confirms the sale order and then makes a POST API call to create a stock order.
        """
        # First, confirm the sale order
        self.action_confirm()

        print("DEBUG: action_confirm_and_create_stock_order called. Starting API calls.")
        api_config = _get_api_config()

        principal_code = "61414"
        customer_ref = "3768712"

        # The logic is applied to the current sale order and its lines.
        for order in self:
            for line in order.order_line:
                try:
                    product_id = line.product_id
                    product_sku = product_id.default_code or 'B001'
                    quantity = int(line.product_uom_qty)

                    print(f"DEBUG: Processing sale order line for product {product_id.display_name} with quantity {quantity}")

                    # --- Prepare and send the updated payload ---
                    reference = f"SO-PO-{order.name}-{product_sku}"
                    payload = {
                        "orderType": "IN",
                        "warehouse": "PWH8",
                        "principalCode": principal_code,
                        "reference": reference,
                        "jobReference": reference,
                        "customerReference": customer_ref,
                        "orderDate": datetime.date.today().isoformat(),
                        "dateWanted": datetime.date.today().isoformat(),
                        "etaDate": datetime.date.today().isoformat(),
                        "instructions": order.partner_id.email or "test@example.com",
                        "orderNotes": order.partner_id.name or "Test Company Ltd",
                        "deliveryDocketNumber": "DN" + reference,
                        "supplierInvoiceNumber": "SI" + reference,
                        "stockMethod": "N",
                        "stockOrderLines": [{
                            "lineNumber": 1,
                            "productCode": product_sku,
                            "ItemDesc": product_id.name or "",
                            "ItemShortdesc": product_id.name[:50] if product_id.name else "",
                            "ItemWidth": getattr(product_id, 'width', 2.0) or 2.0,
                            "ItemLength": getattr(product_id, 'length', 2.0) or 2.0,
                            "ItemHeight": getattr(product_id, 'height', 2.0) or 2.0,
                            "ItemVol": getattr(product_id, 'volume', 1.5) or 1.5,
                            "ItemWeight": getattr(product_id, 'weight', 1.6) or 1.6,
                            "ItemBarcode": product_id.barcode or "12235ASER",
                            "ItemType": "Cartoon",
                            "ItemGroup": "A",
                            "uom": line.product_uom.name or "UNIT",
                            "notes": f"Stock Order for Sale Order: {order.name}",
                            "qtyReceived": quantity,
                            "qtyOrdered": quantity,
                            "gtinBarcode": product_id.barcode or "ABC123"
                        }]
                    }
                    print(f"DEBUG: Payload for product {product_id.name}:", payload)

                    url = "https://push-api-uat.bdladvantage.com/v2/StockOrder"
                    headers = {
                        "Authorization": api_config['api_key'],
                        "Content-Type": "application/json"
                    }

                    print(f"DEBUG: Sending inventory adjustment API request for product {product_id.name}")
                    response = requests.post(url, json=payload, headers=headers, timeout=30)
                    print(f"DEBUG: API response - Status: {response.status_code}, Body: {response.text}")

                    _logger.info("Inventory API POST - Product: %s - Status: %s", product_id.name, response.status_code)

                    if response.status_code not in [200, 201]:
                        error_msg = f"API failed: Status {response.status_code}, Response: {response.text}"
                        _logger.warning(error_msg)
                        order.message_post(body=error_msg, message_type='comment')
                        print(f"DEBUG: API call failed for product {product_id.name}")
                    else:
                        order.message_post(body=f"Stock Order API Success - Status: {response.status_code}", message_type='comment')
                        print(f"DEBUG: API call successful for product {product_id.name}")

                except requests.exceptions.Timeout:
                    error_msg = f"API timeout for product {product_id.name}"
                    _logger.error(error_msg)
                    order.message_post(body="API Timeout", message_type='comment')
                    print(f"DEBUG: {error_msg}")
                except Exception as e:
                    error_msg = f"Exception for product {product_id.name}: {str(e)}"
                    _logger.exception(error_msg)
                    order.message_post(body=f"API Error: {str(e)}", message_type='comment')
                    print(f"DEBUG: {error_msg}")

        return True