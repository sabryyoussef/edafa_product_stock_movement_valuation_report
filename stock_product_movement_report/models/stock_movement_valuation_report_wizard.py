from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class StockMovementValuationReportWizard(models.TransientModel):
    _name = "stock.movement.valuation.report.wizard"
    _description = "Stock Movement Valuation Report Wizard"

    product_id = fields.Many2one("product.product", required=True, string="Product")
    date_from = fields.Date(required=True, string="Date From")
    date_to = fields.Date(required=True, string="Date To")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        string="Company",
    )
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse")
    location_id = fields.Many2one("stock.location", string="Location")
    include_child_locations = fields.Boolean(default=True, string="Include Child Locations")
    show_internal_transfers = fields.Boolean(default=True, string="Show Internal Transfers")
    show_valuation = fields.Boolean(default=True, string="Show Valuation")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError("Date From must be earlier than or equal to Date To.")

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "stock_product_movement_report.action_report_stock_movement_valuation_pdf"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError("You are not allowed to export this report.")
        return {
            "type": "ir.actions.act_url",
            "url": "/stock_product_movement_report/export/xlsx/%s" % self.id,
            "target": "self",
        }
