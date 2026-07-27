{
    "name": "OnePay Payment Provider",
    "version": "19.0.1.1.1",
    "author": "Sanmark Solutions",
    "website": "https://sanmarksolutions.com/",
    "category": "Accounting/Payment Providers",
    "summary": "Accept online payments in Odoo using OnePay payment gateway",
    "description": """
OnePay Payment Provider for Odoo 19.

This module integrates OnePay payment gateway with Odoo.

Features:
- OnePay checkout link integration
- Customer invoice online payment support
- eCommerce checkout payment support
- Webhook and return URL payment status processing
- Automatic payment transaction confirmation
- Accounting payment creation support
- Multi-company compatible configuration
- LKR and USD currency support

Flow:
- Odoo creates a payment transaction.
- Odoo creates a checkout link from OnePay.
- Customer is redirected to OnePay.
- OnePay sends webhook callback.
- Odoo verifies the payment using OnePay transaction status API.
- Odoo confirms the payment transaction and creates the related accounting payment.
""",
    "depends": [
        "payment",
        "account_payment",
    ],
    "data": [
        "data/payment_provider_data.xml",
        "views/payment_provider_views.xml",
    ],
    "images": [
        "static/description/icon.png",
    ],
    "installable": True,
    "application": False,
    "license": "OPL-1",
    "price": 29.00,
    "currency": "USD",
}