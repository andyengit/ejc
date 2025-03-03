from odoo import api,fields, models
import logging
_logger = logging.getLogger(__name__)


class EventRegistration(models.Model):
    _inherit = "event.registration"

    invoice_paid = fields.Boolean(compute="_compute_invoice_paid", string="Pagado?")

    @api.depends("sale_order_id.invoice_ids.state")
    def _compute_invoice_paid(self):
        for registration in self:
            registration.invoice_paid = registration.sale_order_id.invoice_ids.filtered(lambda inv: inv.payment_state == "paid")

