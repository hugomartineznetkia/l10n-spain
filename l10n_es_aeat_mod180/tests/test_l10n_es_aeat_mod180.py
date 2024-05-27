# © 2024 Marián Cuadra <marian.cuadra@netkia.es>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0
import logging

from odoo import exceptions

from odoo.addons.l10n_es_aeat.tests.test_l10n_es_aeat_mod_base import (
    TestL10nEsAeatModBase,
)

_logger = logging.getLogger("aeat")


class TestL10nEsAeatMod180Base(TestL10nEsAeatModBase):
    # Set 'debug' attribute to True to easy debug this test
    # Do not forget to include '--log-handler aeat:DEBUG' in Odoo command line
    debug = False
    taxes_purchase = {
        # tax code: (base, tax_amount)
        "P_IRPF19A": (1000, 190),
        "P_IRPF195A": (2000, 390),
        "P_IRPF20A": (3000, 600),
        "P_IRPF21A": (4000, 840),
    }
    taxes_result = {
        # Base retenciones e ingresos a cuenta
        "2": (
            (2 * 1000)
            + (2 * 2000)
            + (2 * 3000)  # P_IRPF19A, P_IRPF195A
            + (2 * 4000)  # P_IRPF20A, P_IRPF21A
        ),
        # Retenciones e ingresos a cuenta
        "3": (
            (2 * 190)
            + (2 * 390)
            + (2 * 600)  # P_IRPF19A, P_IRPF195A
            + (2 * 840)  # P_IRPF20A, P_IRPF21A
        ),
    }

    @classmethod
    def _invoice_purchase_create_with_real_state(cls, dt, extra_vals=None):
        data = {
            "company_id": cls.company.id,
            "partner_id": cls.supplier.id,
            "invoice_date": dt,
            "move_type": "in_invoice",
            "journal_id": cls.journal_purchase.id,
            "invoice_line_ids": [],
        }
        _logger.debug("Creating purchase invoice: date = %s" % dt)
        if cls.debug:
            _logger.debug("{:>14} {:>9}".format("PURCHASE TAX", "PRICE"))
        for desc, values in cls.taxes_purchase.items():
            if cls.debug:
                _logger.debug("{:>14} {:>9}".format(desc, values[0]))
            # Allow to duplicate taxes skipping the unique key constraint
            line_data = {
                "name": "Test for tax(es) %s" % desc,
                "account_id": cls.accounts["600000"].id,
                "price_unit": values[0],
                "quantity": 1,
            }
            taxes = cls._get_taxes(desc.split("//")[0])
            if taxes:
                line_data["tax_ids"] = [(4, t.id) for t in taxes]
            data["invoice_line_ids"].append((0, 0, line_data))
        if extra_vals:
            data.update(extra_vals)
        inv = cls.env["account.move"].with_user(cls.billing_user).create(data)
        inv.sudo().action_post()  # FIXME: Why do we need to do it as sudo?
        if cls.debug:
            cls._print_move_lines(inv.line_ids)
        return inv

    @classmethod
    def _create_model_180(cls):
        export_config = cls.env.ref(
            "l10n_es_aeat_mod180.aeat_mod_180_main_export_config"
        )
        return cls.env["l10n.es.aeat.mod180.report"].create(
            {
                "name": "9990000000180",
                "company_id": cls.company.id,
                "company_vat": "1234567890",
                "contact_name": "Test owner",
                "statement_type": "N",
                "support_type": "T",
                "contact_phone": "911234455",
                "year": 2023,
                "period_type": "0A",
                "date_start": "2023-01-01",
                "date_end": "2023-12-31",
                "export_config_id": export_config.id,
                "journal_id": cls.journal_misc.id,
                "counterpart_account_id": cls.accounts["475000"].id,
            }
        )

    def test_model_180(self):
        # Purchase invoices
        self._invoice_purchase_create("2023-01-01")
        self._invoice_purchase_create("2023-04-02")
        purchase = self._invoice_purchase_create("2023-06-03")
        self._invoice_refund(purchase, "2023-01-18")
        self.model180 = self._create_model_180()
        self.model180.button_calculate()
        self.assertEqual(self.model180.tipo_declaracion, "I")
        self.assertEqual(self.model180.tipo_declaracion_positiva, "I")
        self.assertFalse(self.model180.tipo_declaracion_negativa)
        with self.assertRaises(exceptions.ValidationError):
            self.model180.tipo_declaracion = "N"
        # Fill manual fields
        self.model180.write(
            {
                # Resultados a ingresar anteriores
                "casilla_04": 145,
                "tipo_declaracion_positiva": "U",
            }
        )
        # Check tax lines
        for box, result in self.taxes_result.items():
            lines = self.model180.tax_line_ids.filtered(
                lambda x: x.field_number == int(box)
            )
            self.assertEqual(round(sum(lines.mapped("amount")), 2), round(result, 2))
        # Check result
        retenciones = self.taxes_result.get("3", 0.0)
        result = retenciones - 145
        self.assertEqual(self.model180.casilla_01, 1)
        self.assertEqual(round(self.model180.casilla_03, 2), round(retenciones, 2))
        self.assertEqual(round(self.model180.casilla_05, 2), round(result, 2))
        with self.assertRaises(exceptions.UserError):
            self.model180.button_confirm()
        self.model180.partner_bank_id = self.customer_bank.id
        self.model180.button_confirm()

    def test_negative_model_180(self):
        # Make the invoice in a different period for having negative result
        purchase = self._invoice_purchase_create("2023-01-01")
        self._invoice_refund(purchase, "2023-11-18")
        self.model180 = self._create_model_180()
        self.model180.button_calculate()
        self.assertEqual(self.model180.tipo_declaracion, "N")
        self.assertEqual(self.model180.tipo_declaracion_negativa, "N")
        self.assertFalse(self.model180.tipo_declaracion_positiva)
        with self.assertRaises(exceptions.ValidationError):
            self.model180.tipo_declaracion = "I"
        # this doesn't rise any error
        self.model180.tipo_declaracion_negativa = "N"
