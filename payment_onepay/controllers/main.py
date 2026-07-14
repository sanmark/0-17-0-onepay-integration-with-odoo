import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class OnePayController(http.Controller):

    def _json_response(self, data, status=200):
        response = request.make_response(
            json.dumps(data),
            headers=[
                ("Content-Type", "application/json"),
            ],
        )
        response.status_code = status
        return response

    def _get_json_payload(self):
        payload = request.httprequest.get_json(silent=True)

        if isinstance(payload, dict):
            return payload

        return dict(request.params)

    def _process_onepay_payload(self, payload):
        Transaction = request.env["payment.transaction"].sudo()

        tx = Transaction._get_tx_from_notification_data("onepay", payload)
        verified_data = tx._onepay_verify_status(payload)

        processed_tx = False

        # Odoo 19 style
        if hasattr(Transaction, "_process"):
            processed_tx = Transaction._process("onepay", verified_data)

        # Older fallback
        elif hasattr(Transaction, "_handle_notification_data"):
            processed_tx = Transaction._handle_notification_data("onepay", verified_data)

        else:
            tx._process_notification_data(verified_data)
            processed_tx = tx

        if processed_tx and processed_tx.state == "done" and not processed_tx.is_post_processed:
            processed_tx.sudo()._post_process()

        return processed_tx

    @http.route(
        "/payment/onepay/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def onepay_webhook(self, **kwargs):
        payload = self._get_json_payload()

        _logger.info("OnePay webhook received: %s", payload)

        try:
            self._process_onepay_payload(payload)

        except Exception as error:
            _logger.exception("OnePay webhook processing failed.")

            return self._json_response({
                "status": "error",
                "message": str(error),
            }, status=400)

        return self._json_response({
            "status": "ok",
        })

    @http.route(
        "/payment/onepay/return",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
        website=True,
    )
    def onepay_return(self, **kwargs):
        payload = self._get_json_payload()

        _logger.info("OnePay return received: %s", payload)

        try:
            if payload:
                self._process_onepay_payload(payload)

        except Exception:
            _logger.exception("OnePay return processing failed.")

        return request.redirect("/payment/status")