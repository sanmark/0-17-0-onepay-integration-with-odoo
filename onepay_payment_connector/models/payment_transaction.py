import hashlib
import logging

from urllib.parse import quote_plus

import requests

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    # -------------------------------------------------------------------------
    # OnePay helpers
    # -------------------------------------------------------------------------

    def _onepay_generate_hash(self, amount_string):
        self.ensure_one()

        provider = self.provider_id

        raw_value = "%s%s%s%s" % (
            provider.onepay_app_id or "",
            self.currency_id.name or "",
            amount_string,
            provider.onepay_hash_salt or "",
        )

        return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()

    def _onepay_post(self, endpoint, payload):
        self.ensure_one()

        provider = self.provider_id
        url = provider._onepay_get_api_url(endpoint)

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": provider.onepay_app_token or "",
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as error:
            raise ValidationError(_("OnePay connection failed: %s") % error)

        try:
            response_json = response.json()
        except ValueError:
            response_json = {}

        if response.status_code >= 400:
            raise ValidationError(
                _("OnePay API error. Status: %(status)s. Response: %(response)s") % {
                    "status": response.status_code,
                    "response": response.text,
                }
            )

        return response_json

    def _onepay_get_nested_value(self, data, *keys):
        if not isinstance(data, dict):
            return False

        for key in keys:
            if key in data:
                return data.get(key)

        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            for key in keys:
                if key in nested_data:
                    return nested_data.get(key)

        return False

    def _onepay_get_partner_names(self):
        self.ensure_one()

        full_name = (self.partner_name or self.partner_id.name or "Customer").strip()
        name_parts = full_name.split(" ", 1)

        first_name = name_parts[0] or "Customer"
        last_name = name_parts[1] if len(name_parts) > 1 else "Odoo"

        return first_name, last_name

    def _onepay_get_customer_phone(self):
        self.ensure_one()

        transaction_phone = ""
        if "partner_phone" in self._fields:
            transaction_phone = self.partner_phone or ""

        phone = (
            transaction_phone
            or self.partner_id.phone
            or self.partner_id.mobile
            or ""
        ).strip()

        phone = phone.replace(" ", "").replace("-", "")

        if not phone:
            raise ValidationError(
                _("OnePay requires the customer phone number. Please set phone/mobile on the customer.")
            )

        return phone

    def _onepay_get_customer_email(self):
        self.ensure_one()

        transaction_email = ""
        if "partner_email" in self._fields:
            transaction_email = self.partner_email or ""

        email = (
            transaction_email
            or self.partner_id.email
            or ""
        ).strip()

        if not email:
            raise ValidationError(
                _("OnePay requires the customer email address. Please set email on the customer.")
            )

        return email

    def _onepay_is_success_status(self, status, status_message=False):
        if status is True:
            return True

        if isinstance(status, int) and status == 1:
            return True

        if isinstance(status, str) and status.lower() in [
            "true",
            "1",
            "success",
            "paid",
            "completed",
        ]:
            return True

        if isinstance(status_message, str) and status_message.lower() in [
            "success",
            "paid",
            "completed",
        ]:
            return True

        return False

    # -------------------------------------------------------------------------
    # Odoo payment rendering
    # -------------------------------------------------------------------------

    def _get_specific_rendering_values(self, processing_values):
        rendering_values = super()._get_specific_rendering_values(processing_values)

        if self.provider_code != "onepay":
            return rendering_values

        self.ensure_one()

        provider = self.provider_id

        if not provider.onepay_app_id or not provider.onepay_app_token or not provider.onepay_hash_salt:
            raise ValidationError(_("Please configure OnePay App ID, App Token and Hash Salt."))

        amount_string = "%.2f" % self.amount
        first_name, last_name = self._onepay_get_partner_names()

        base_url = self.env["ir.config_parameter"].sudo().get_str(
            "web.base.url",
            "",
        ).rstrip("/")

        if not base_url:
            raise ValidationError(_("System parameter web.base.url is not configured."))

        odoo_reference = self.reference or str(self.id)

        onepay_reference = odoo_reference
        if len(onepay_reference) < 10:
            onepay_reference = "ODOO-%s-%s" % (odoo_reference, self.id)

        payload = {
            "app_id": provider.onepay_app_id,
            "amount": amount_string,
            "currency": self.currency_id.name,
            "hash": self._onepay_generate_hash(amount_string),
            "reference": onepay_reference,
            "customer_first_name": first_name,
            "customer_last_name": last_name,
            "customer_phone_number": self._onepay_get_customer_phone(),
            "customer_email": self._onepay_get_customer_email(),
            "transaction_redirect_url": "%s/payment/onepay/return?reference=%s" % (
                base_url,
                quote_plus(self.reference or ""),
            ),
            "additionalData": odoo_reference,
        }

        _logger.info("Creating OnePay transaction for Odoo reference %s", self.reference)

        response_json = self._onepay_post("/v3/checkout/link/", payload)

        gateway_data = {}
        if isinstance(response_json.get("data"), dict):
            gateway_data = response_json["data"].get("gateway") or {}

        redirect_url = (
            self._onepay_get_nested_value(
                response_json,
                "redirect_url",
                "payment_url",
                "checkout_url",
            )
            or gateway_data.get("redirect_url")
        )

        onepay_transaction_id = self._onepay_get_nested_value(
            response_json,
            "ipg_transaction_id",
            "transaction_id",
            "onepay_transaction_id",
        )

        if not redirect_url:
            raise ValidationError(
                _("OnePay did not return redirect_url. Response: %s") % response_json
            )

        if onepay_transaction_id:
            self.provider_reference = onepay_transaction_id

        return {
            "api_url": redirect_url,
            "reference": self.reference,
        }

    # -------------------------------------------------------------------------
    # OnePay verification
    # -------------------------------------------------------------------------

    def _onepay_verify_status(self, callback_payload):
        self.ensure_one()

        onepay_transaction_id = (
            callback_payload.get("transaction_id")
            or callback_payload.get("ipg_transaction_id")
            or callback_payload.get("onepay_transaction_id")
            or self.provider_reference
        )

        if not onepay_transaction_id:
            raise ValidationError(
                _("OnePay callback did not contain transaction_id and provider_reference is empty.")
            )

        payload = {
            "app_id": self.provider_id.onepay_app_id,
            "onepay_transaction_id": onepay_transaction_id,
        }

        response_json = self._onepay_post("/v3/transaction/status/", payload)

        # OnePay may return API status at top-level:
        # {"status": 200, "message": "...", "data": {...}}
        # The real payment status should be read from data.status.
        response_data = response_json.get("data")
        if not isinstance(response_data, dict):
            response_data = response_json

        status = response_data.get("status")

        # Fallback to callback status if status API does not return payment status.
        if status in [None, False, ""]:
            status = callback_payload.get("status")

        amount = (
            response_data.get("amount")
            or response_data.get("gross_amount")
            or response_data.get("net_amount")
            or response_json.get("amount")
        )

        currency = (
            response_data.get("currency")
            or response_json.get("currency")
            or self.currency_id.name
        )

        status_message = (
            response_data.get("status_message")
            or response_data.get("message")
            or response_json.get("status_message")
            or response_json.get("message")
            or callback_payload.get("status_message")
        )

        provider_reference = (
            response_data.get("ipg_transaction_id")
            or response_data.get("transaction_id")
            or response_data.get("onepay_transaction_id")
            or response_json.get("ipg_transaction_id")
            or response_json.get("transaction_id")
            or response_json.get("onepay_transaction_id")
            or onepay_transaction_id
        )

        return {
            "reference": self.reference,
            "provider_reference": provider_reference,
            "status": status,
            "status_message": status_message,
            "amount": amount,
            "currency": currency,
            "raw_response": response_json,
        }

    # -------------------------------------------------------------------------
    # Odoo notification handling
    # -------------------------------------------------------------------------

    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != "onepay":
            return super()._search_by_reference(provider_code, payment_data)

        reference = (
            payment_data.get("reference")
            or payment_data.get("additional_data")
            or payment_data.get("additionalData")
        )

        provider_reference = (
            payment_data.get("provider_reference")
            or payment_data.get("transaction_id")
            or payment_data.get("ipg_transaction_id")
            or payment_data.get("onepay_transaction_id")
        )

        base_domain = Domain("provider_code", "=", "onepay")

        if provider_reference:
            tx = self.search(
                Domain.AND([base_domain, Domain("provider_reference", "=", provider_reference)]),
                limit=1,
            )
            if tx:
                return tx

        if reference:
            tx = self.search(
                Domain.AND([base_domain, Domain("reference", "=", reference)]),
                limit=1,
            )
            if tx:
                return tx

        raise ValidationError(
            _("No OnePay transaction found for data: %s") % payment_data
        )

    def _extract_reference(self, provider_code, payment_data):
        if provider_code != "onepay":
            return super()._extract_reference(provider_code, payment_data)

        return (
            payment_data.get("reference")
            or payment_data.get("additional_data")
            or payment_data.get("additionalData")
        )

    def _extract_amount_data(self, payment_data):
        if self.provider_code != "onepay":
            return super()._extract_amount_data(payment_data)

        amount = payment_data.get("amount")
        currency_code = payment_data.get("currency")

        # Let the framework skip amount/currency validation when the verified
        # data does not carry them. When present, Odoo 20 core compares these
        # against the expected transaction amount/currency and sets the error
        # state itself on mismatch.
        if amount in (None, False, "") or not currency_code:
            return None

        return {
            "amount": float(amount),
            "currency_code": currency_code,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != "onepay":
            return super()._apply_updates(payment_data)

        self.ensure_one()
        self._onepay_apply_payment_status(payment_data)

    # -------------------------------------------------------------------------
    # Shared status application
    # -------------------------------------------------------------------------

    def _onepay_apply_payment_status(self, payment_data):
        """Apply verified OnePay payment data to the transaction.

        Invoked by Odoo 20 core through ``_apply_updates`` inside ``_process``,
        which itself runs under the ``payment_safe_write`` context queued by
        ``_record``. Direct field writes (``provider_reference``) are therefore
        allowed here. Amount and currency are validated by core via
        ``_extract_amount_data``; this method only records the provider
        reference and sets the final state, idempotently.
        """
        self.ensure_one()

        # Idempotency: never re-process or downgrade a finalized transaction.
        # Webhook and browser-return can both deliver the same notification.
        allowed_to_modify = self.state not in ("done", "authorized")
        if not allowed_to_modify:
            _logger.info(
                "OnePay: transaction %s already in state '%s'; skipping re-processing.",
                self.reference, self.state,
            )
            return

        provider_reference = payment_data.get("provider_reference")
        if provider_reference:
            self.provider_reference = provider_reference

        status = payment_data.get("status")
        status_message = payment_data.get("status_message")

        if self._onepay_is_success_status(status, status_message):
            _logger.info(
                "OnePay: marking transaction %s as done (status=%s).",
                self.reference, status,
            )
            self._set_done()
        else:
            _logger.info(
                "OnePay: marking transaction %s as error (status=%s, message=%s).",
                self.reference, status, status_message,
            )
            self._set_error(
                _("OnePay payment was not successful. Status: %(status)s. Message: %(message)s") % {
                    "status": status,
                    "message": status_message or "",
                }
            )