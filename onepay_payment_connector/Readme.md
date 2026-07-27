# OnePay Payment Provider for Odoo 19

OnePay Payment Provider integrates the OnePay payment gateway with Odoo 19.

## Features

- OnePay checkout link integration
- Customer invoice online payment support
- eCommerce checkout payment support
- Webhook payment status handling
- Return URL payment status handling
- Automatic payment transaction confirmation
- Accounting payment creation support
- Multi-company compatible setup
- LKR and USD currency support

## Supported Odoo Version

- Odoo 19.0

## Dependencies

- payment
- account_payment

## Configuration

1. Install the module.
2. Go to Accounting > Configuration > Payment Providers.
3. Open OnePay.
4. Enter:
   - OnePay App ID
   - OnePay App Token
   - OnePay Hash Salt
   - OnePay API Base URL
5. Select the payment journal.
6. Configure allowed currencies and countries if required.
7. Enable the payment provider.
8. Configure the callback URL in the OnePay merchant portal.

## Callback URL

Use the following callback path:

```text
/payment/onepay/webhook