from odoo import api, fields, models
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class EventRegistration(models.Model):
    _inherit = "event.registration"

    invoice_paid = fields.Boolean(compute="_compute_invoice_paid", string="Pagado?")

    @api.depends("sale_order_id.invoice_ids.state")
    def _compute_invoice_paid(self):
        for registration in self:
            registration.invoice_paid = registration.sale_order_id.invoice_ids.filtered(
                lambda inv: inv.payment_state == "paid"
            )

    @api.model
    def register_attendee(self, barcode, event_id):
        res = super(EventRegistration, self).register_attendee(barcode, event_id)
        res.update({"has_to_pay": not self.invoice_paid})
        return res


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_create_invoice_and_payment(self):
        # Crear la factura desde el presupuesto de venta
        invoices = self._create_invoices()

        if not invoices:
            raise UserError("No se pudo crear la factura para el presupuesto: %s" % self.name)

        invoice = invoices[0]  # Tomar la primera factura si se crean varias

        invoice.action_post()

        # Obtener el diario y el método de pago
        journal = self.env["account.journal"].browse(6)
        if not journal:
            raise UserError("No se encontró el diario con ID 6.")

        # Acceder al método de pago a través de inbound_payment_method_line_ids
        payment_method_line = journal.inbound_payment_method_line_ids[:1]  # Tomar la primera línea de método de pago
        if not payment_method_line:
            raise UserError("No hay métodos de pago configurados para el diario con ID 6.")

        payment_method = payment_method_line.payment_method_id

        if not payment_method:
            raise UserError("No se encontró el método de pago en la línea del diario.")

        # Crear el pago
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_id.id,
                "amount": invoice.amount_total,
                "date": fields.Date.today(),
                "journal_id": journal.id,
                "payment_method_id": payment_method.id,
                "ref": self.name + " - " + self.client_order_ref,  # Referencia al presupuesto de venta
                "currency_id": invoice.currency_id.id,
            }
        )

        # Validar el pago
        payment.action_post()

        # Obtener las líneas de la factura y del pago que se van a reconciliar
        invoice_account_id = invoice.invoice_line_ids.account_id
        invoice_lines = invoice.invoice_line_ids.filtered(
            lambda l: l.account_id == invoice_account_id and not l.reconciled
        )
        payment_lines = payment.line_ids.filtered(lambda l: l.account_id == invoice_account_id and not l.reconciled)

        # Reconciliar las líneas
        for line in payment_lines + invoice_lines:
            if line.account_id.reconcile:
                try:
                    line.reconcile()
                except Exception as e:
                    raise UserError("Error al reconciliar la línea: %s" % e)

        action = {
            "type": "ir.actions.act_window",
            "name": "Factura",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "target": "current",
        }

        return action
