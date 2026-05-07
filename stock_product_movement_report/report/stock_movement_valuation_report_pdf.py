from odoo import models


class ReportStockMovementValuation(models.AbstractModel):
    _name = "report.stock_product_movement_report.rpt_stock_move_valuation_doc"
    _description = "Stock Movement Valuation PDF Report"
    _table = "report_spmv_doc"

    def _get_report_values(self, docids, data=None):
        docs = self.env["stock.movement.valuation.report.wizard"].browse(docids)
        service = self.env["stock.movement.valuation.report.service"]
        report_data = {}
        if docs:
            report_data = service.prepare_report_data(docs[0])
        return {
            "doc_ids": docs.ids,
            "doc_model": "stock.movement.valuation.report.wizard",
            "docs": docs,
            "report_data": report_data,
            "payload": report_data,
        }
