{
    "name": "OnePay Payment Provider",
    "version": "20.0.1.0.0",
    "author": "Sanmark Solutions",
    "category": "Accounting/Payment Providers",
    "summary": "OnePay payment gateway integration for Odoo",
    "description": """
OnePay payment gateway integration for Odoo.

Flow:
- Odoo creates payment.transaction
- Odoo creates checkout link from OnePay
- Customer is redirected to OnePay
- OnePay sends webhook callback
- Odoo verifies payment using OnePay transaction status API
""",
    "depends": ["payment", "account_payment"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "data/payment_provider_data.xml",
        "views/payment_provider_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}