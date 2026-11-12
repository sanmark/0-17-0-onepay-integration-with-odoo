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

        # Locate the transaction so we can run the server-to-server status
        # confirmation before trusting any callback data.
        tx = Transaction._search_by_reference("onepay", payload)
        verified_data = tx._onepay_verify_status(payload)

        # Odoo 20 orchestrates extraction + updates through _process().
        tx._process(verified_data)

        if tx.state == "done" and not tx.is_post_processed:
            tx.sudo()._post_process()

        return tx

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