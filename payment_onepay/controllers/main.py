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

        Transaction = request.env["payment.transaction"].sudo()

        try:
            tx = Transaction._get_tx_from_notification_data("onepay", payload)
            verified_data = tx._onepay_verify_status(payload)

            if hasattr(Transaction, "_process"):
                Transaction._process("onepay", verified_data)

            elif hasattr(Transaction, "_handle_notification_data"):
                Transaction._handle_notification_data("onepay", verified_data)

            else:
                tx._process_notification_data(verified_data)

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
        return request.redirect("/payment/status")