from odoo import fields, models


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("onepay", "OnePay")],
        ondelete={"onepay": "set default"},
    )

    onepay_app_id = fields.Char(
        string="OnePay App ID",
        required_if_provider="onepay",
    )

    onepay_app_token = fields.Char(
        string="OnePay App Token",
        required_if_provider="onepay",
        groups="base.group_system",
    )

    onepay_hash_salt = fields.Char(
        string="OnePay Hash Salt",
        required_if_provider="onepay",
        groups="base.group_system",
    )

    onepay_api_base_url = fields.Char(
        string="OnePay API Base URL",
        default="https://api.onepay.lk",
        required_if_provider="onepay",
        help="Default: https://api.onepay.lk",
    )

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()

        for provider in self.filtered(lambda p: p.code == "onepay"):
            if "support_tokenization" in provider._fields:
                provider.support_tokenization = False

            if "support_manual_capture" in provider._fields:
                provider.support_manual_capture = False

            if "support_refund" in provider._fields:
                provider.support_refund = "none"

            if "support_express_checkout" in provider._fields:
                provider.support_express_checkout = False

    def _get_default_payment_method_codes(self):
        self.ensure_one()

        if self.code != "onepay":
            return super()._get_default_payment_method_codes()

        return ["onepay"]

    def _get_supported_currencies(self):
        self.ensure_one()

        if self.code != "onepay":
            return super()._get_supported_currencies()

        return self.env["res.currency"].search([
            ("name", "in", ["LKR", "USD"])
        ])

    def _onepay_get_api_base_url(self):
        self.ensure_one()
        return (self.onepay_api_base_url or "https://api.onepay.lk").rstrip("/")

    def _onepay_get_api_url(self, endpoint):
        self.ensure_one()

        return "%s/%s" % (
            self._onepay_get_api_base_url(),
            endpoint.lstrip("/"),
        )