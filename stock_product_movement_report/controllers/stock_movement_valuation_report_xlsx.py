import io

from odoo import http
from odoo.http import content_disposition, request
from odoo.tools.misc import xlsxwriter


class StockMovementValuationReportXlsxController(http.Controller):
    def _build_workbook_bytes(self, data):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Movement Valuation")

        fmt_title = workbook.add_format({"bold": True, "font_size": 14})
        fmt_subtitle = workbook.add_format({"italic": True, "font_size": 10})
        fmt_header = workbook.add_format({"bold": True, "bg_color": "#E9ECEF", "border": 1})
        fmt_cell = workbook.add_format({"border": 1, "text_wrap": True})
        fmt_num = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        fmt_label = workbook.add_format({"bold": True, "border": 1, "bg_color": "#F8F9FA"})

        row = 0
        sheet.merge_range(row, 0, row, 10, "Product Movement Valuation Report", fmt_title)
        row += 1
        sheet.merge_range(row, 0, row, 10, "تقرير حركة وتقييم الصنف", fmt_subtitle)
        row += 2

        header = data.get("header", {})
        header_rows = [
            ("Company", header.get("company_name")),
            ("Product", header.get("product_name")),
            ("Internal Reference", header.get("product_code")),
            ("UoM", header.get("uom")),
            ("Cost Method", header.get("cost_method")),
            ("Date From", header.get("date_from")),
            ("Date To", header.get("date_to")),
            ("Warehouse", header.get("warehouse")),
            ("Location", header.get("location")),
            ("Scope Note", "Running balances are calculated within the selected date/location scope."),
        ]
        for label, value in header_rows:
            sheet.write(row, 0, label, fmt_label)
            sheet.merge_range(row, 1, row, 6, value or "-", fmt_cell)
            row += 1
        row += 1

        sheet.write(row, 0, "Current Stock by Location", fmt_title)
        row += 1
        sheet.write_row(row, 0, ["Location", "Quantity", "Value"], fmt_header)
        row += 1
        for stock_line in data.get("current_stock", []):
            sheet.write(row, 0, stock_line.get("location") or "-", fmt_cell)
            qty = stock_line.get("qty")
            if isinstance(qty, (int, float)):
                sheet.write_number(row, 1, qty, fmt_num)
            else:
                sheet.write(row, 1, "-", fmt_cell)
            val = stock_line.get("value")
            if isinstance(val, (int, float)):
                sheet.write_number(row, 2, val, fmt_num)
            else:
                sheet.write(row, 2, "-", fmt_cell)
            row += 1
        if not data.get("current_stock"):
            sheet.write(row, 0, "-", fmt_cell)
            sheet.write(row, 1, "-", fmt_cell)
            sheet.write(row, 2, "-", fmt_cell)
            row += 1
        row += 1

        sheet.write(row, 0, "Movements", fmt_title)
        row += 1
        movement_headers = [
            "Movement Date",
            "Valuation Date",
            "Document",
            "Origin",
            "Lot/Serial",
            "Expiry",
            "From",
            "To",
            "Type",
            "Incoming Qty",
            "Incoming Unit Cost",
            "Incoming Value",
            "Outgoing Qty",
            "Outgoing Unit Cost",
            "Outgoing Value",
            "Balance Qty",
            "Balance Avg Cost",
            "Balance Value",
            "Notes",
        ]
        sheet.write_row(row, 0, movement_headers, fmt_header)
        header_row_for_freeze = row
        row += 1

        for mv_row in data.get("rows", []):
            values = [
                mv_row.get("movement_date"),
                mv_row.get("valuation_date"),
                mv_row.get("document_ref"),
                mv_row.get("origin"),
                mv_row.get("lot"),
                mv_row.get("expiry_date"),
                mv_row.get("source_location"),
                mv_row.get("dest_location"),
                mv_row.get("movement_type"),
                mv_row.get("incoming_qty"),
                mv_row.get("incoming_unit_cost"),
                mv_row.get("incoming_value"),
                mv_row.get("outgoing_qty"),
                mv_row.get("outgoing_unit_cost"),
                mv_row.get("outgoing_value"),
                mv_row.get("running_qty"),
                mv_row.get("running_avg_cost"),
                mv_row.get("running_value"),
                mv_row.get("notes"),
            ]
            for col, value in enumerate(values):
                if isinstance(value, (int, float)):
                    sheet.write_number(row, col, value, fmt_num)
                else:
                    sheet.write(row, col, value if value not in ("", None, False) else "-", fmt_cell)
            row += 1
        if not data.get("rows"):
            sheet.merge_range(row, 0, row, 18, "No movements found for the selected filters.", fmt_cell)
            row += 1
        row += 1

        sheet.write(row, 0, "Totals", fmt_title)
        row += 1
        totals_headers = [
            "Incoming Qty",
            "Incoming Value",
            "Outgoing Qty",
            "Outgoing Value",
            "Ending Qty",
            "Ending Value",
        ]
        totals = data.get("totals", {})
        totals_values = [
            totals.get("incoming_qty"),
            totals.get("incoming_value"),
            totals.get("outgoing_qty"),
            totals.get("outgoing_value"),
            totals.get("ending_qty"),
            totals.get("ending_value"),
        ]
        sheet.write_row(row, 0, totals_headers, fmt_header)
        row += 1
        for col, value in enumerate(totals_values):
            if isinstance(value, (int, float)):
                sheet.write_number(row, col, value, fmt_num)
            else:
                sheet.write(row, col, "-", fmt_cell)
        row += 2

        sheet.write(row, 0, "Warnings", fmt_title)
        row += 1
        for warning in data.get("warnings", []):
            sheet.merge_range(row, 0, row, 12, warning, fmt_cell)
            row += 1
        if not data.get("warnings"):
            sheet.merge_range(row, 0, row, 12, "-", fmt_cell)
            row += 1
        row += 1

        sheet.write(row, 0, "Flag Legend", fmt_title)
        row += 1
        sheet.write_row(row, 0, ["Flag", "Meaning"], fmt_header)
        row += 1
        legend_rows = [
            ("ZERO_VALUE_SVL", "Valuation layer exists but value is zero."),
            ("NEGATIVE_RUNNING_QTY", "Running quantity is negative within selected scope."),
            ("VAL_LINK_MISSING", "No valuation layer was safely linked to this movement."),
            ("MULTI_SVL_AMBIGUOUS", "Multiple valuation layers exist and cannot be safely allocated."),
            ("BACKDATED_VALUATION_DATE", "Movement date differs from valuation creation date."),
        ]
        for flag, meaning in legend_rows:
            sheet.write(row, 0, flag, fmt_cell)
            sheet.write(row, 1, meaning, fmt_cell)
            row += 1

        sheet.set_column(0, 0, 20)
        sheet.set_column(1, 1, 26)
        sheet.set_column(2, 8, 18)
        sheet.set_column(9, 17, 14)
        sheet.set_column(18, 18, 30)
        sheet.freeze_panes(header_row_for_freeze + 1, 0)

        workbook.close()
        output.seek(0)
        return output.getvalue()

    @http.route(
        "/stock_product_movement_report/export/xlsx/<int:wizard_id>",
        type="http",
        auth="user",
    )
    def export_stock_movement_valuation_xlsx(self, wizard_id, **kwargs):
        if not request.env.user.has_group("stock.group_stock_manager"):
            return request.not_found()

        wizard = request.env["stock.movement.valuation.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            return request.not_found()
        if wizard.create_uid and wizard.create_uid != request.env.user:
            return request.not_found()
        data = request.env["stock.movement.valuation.report.service"].prepare_report_data(wizard)
        file_content = self._build_workbook_bytes(data)
        filename = "Product_Movement_Valuation_%s.xlsx" % wizard.id
        return request.make_response(
            file_content,
            headers=[
                (
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )
