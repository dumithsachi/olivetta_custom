import logging
import requests
import os
from odoo import models

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


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_update_po(self):
        """
        Custom method to update an external API based on purchase order details.
        Updates the custom field x_studio_note (created via Odoo Studio).
        """
        self.env.cr.commit()

        api_config = _get_api_config()

        principal_code = "61414"
        customer_ref = "3768712"

        for order in self:
            for line in order.order_line:
                try:
                    product_id = line.product_id
                    product_sku = product_id.default_code or 'B001'
                    new_quantity_entered = int(line.product_qty)

                    # --- STEP 1: Get current qty from API ---
                    current_qty_from_api = 0
                    get_url = f"https://push-api-uat.bdladvantage.com/v2/StockOrder/{principal_code}/{customer_ref}"
                    headers = {
                        "Authorization": api_config['api_key'],
                        "Content-Type": "application/json"
                    }
                    get_response = requests.get(get_url, headers=headers, timeout=30)

                    if get_response.status_code in [200, 201]:
                        try:
                            data = get_response.json()
                            for order_data in data.get("productStockOrders", []):
                                for line_data in order_data.get("lines", []):
                                    if str(line_data.get("sku", '')).strip() == str(product_sku).strip():
                                        current_qty_from_api = int(line_data.get("qty", 0))
                                        break
                        except Exception as e:
                            _logger.error("Failed to parse JSON response: %s", str(e))
                            order.message_post(body="Failed to parse API response.", message_type='comment')
                    else:
                        order.message_post(
                            body=f"Failed to retrieve current quantity from API. Status: {get_response.status_code}",
                            message_type='comment')
                    # Get the Purchase Order "Order Deadline" (field = date_order)
                    order_deadline = order.date_order

                    # Get the line "Scheduled Date" (field = date_planned)
                    line_deadline = line.date_planned

                    # Convert to string format (ISO 8601)
                    order_deadline_str = order_deadline.strftime("%Y-%m-%dT%H:%M:%S") if order_deadline else None
                    line_deadline_str = line_deadline.strftime("%Y-%m-%dT%H:%M:%S") if line_deadline else None

                    # --- STEP 2: Calculate new total qty ---
                    new_total_qty = current_qty_from_api + int(new_quantity_entered)

                    # --- STEP 3: Prepare payload ---
                    reference = f"INV-ADJ-{product_sku or product_id.id}"
                    payload = {
                        "orderType": "IN",
                        "warehouse": "PWH8",
                        "principalCode": principal_code,
                        "reference": reference,
                        "jobReference": reference,
                        "customerReference": customer_ref,
                        "orderDate": order_deadline_str,
                        "dateWanted": order_deadline_str,
                        "etaDate": line_deadline_str,
                        "instructions": "test@example.com",
                        "orderNotes": "Test Company Ltd",
                        "deliveryDocketNumber": reference,
                        "supplierInvoiceNumber": reference,
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
                            "notes": f"Inventory Adjustment - Product: {product_id.name}",
                            "qtyReceived": int(new_quantity_entered),
                            "qtyOrdered": new_total_qty,
                            "gtinBarcode": product_id.barcode or "ABC123"
                        }]
                    }

                    # --- STEP 4: Post payload to API ---
                    url = "https://push-api-uat.bdladvantage.com/v2/StockOrder"
                    response = requests.post(url, json=payload, headers=headers, timeout=30)

                    if response.status_code not in [200, 201]:
                        error_msg = f"API failed: Status {response.status_code}, Response: {response.text}"
                        _logger.warning(error_msg)
                        order.message_post(body=error_msg, message_type='comment')
                    else:
                        try:
                            response_data = response.json()
                            api_note = response_data.get('productStockOrder', {}).get('orderNo', False)
                            if api_note:
                                # Update the Studio custom field
                                order.x_studio_bdynamic_note = api_note
                                order.message_post(body=f"Note from API: {api_note}", message_type='comment')
                            else:
                                order.message_post(body="API call successful, but no 'orderNo' value found in response.", message_type='comment')
                        except Exception as e:
                            _logger.error("Failed to parse POST API response JSON: %s", str(e))
                            order.message_post(body="Failed to parse POST API response.", message_type='comment')

                except requests.exceptions.Timeout:
                    order.message_post(body="API Timeout", message_type='comment')
                except Exception as e:
                    _logger.exception("Exception during API call: %s", str(e))
                    order.message_post(body=f"API Error: {str(e)}", message_type='comment')

        return True
