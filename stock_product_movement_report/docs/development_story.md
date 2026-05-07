# Product Movement Valuation Report - Development Story

## 1) Planning and Scope

The module started with a strict scope:

- Build a new Odoo 18 custom module: `stock_product_movement_report`
- Provide a wizard-driven report under **Inventory > Reporting**
- Output formats: PDF and XLSX
- Report is **audit/read-only** only
- No stock recalculation and no writes to stock/accounting records

Core planning decisions:

- Movement source: `stock.move.line`
- Valuation source: `stock.valuation.layer`
- Current stock source: `stock.quant`
- Shared service method to keep PDF/XLSX data identical: `prepare_report_data(wizard)`
- Include audit flags for data-quality and traceability

## 2) Module Foundation

Initial implementation delivered a clean, installable module skeleton:

- Manifest, init files, and dependencies
- Security ACL for `stock.group_stock_manager`
- Wizard model + form view + menu/action
- Placeholder report action and template

This ensured the module could be installed and opened safely before adding business logic.

## 3) Reporting Service Contract

A dedicated service model was introduced:

- Model: `stock.movement.valuation.report.service`
- Method: `prepare_report_data(self, wizard)`

The service returns a structured payload containing:

- Header information
- Current stock by location
- Opening balances
- Movement rows
- Totals
- Warnings

This contract became the single source for both PDF and XLSX output.

## 4) Quantity and Scope Logic

Real movement quantities were then implemented from `stock.move.line` with validated scope rules:

- Warehouse scope uses `warehouse.lot_stock_id` hierarchy
- Historical correctness uses `active_test=False` for archived locations
- Done quantity field in Odoo 18: `stock.move.line.quantity`
- Primary movement date: `stock.move.line.date`

Running quantity and opening quantity were computed in selected date/location scope.

## 5) Valuation Integration

Valuation display was added using `stock.valuation.layer` with safe-linking rules:

- Batch map SVLs by `stock_move_id` (lot-aware when possible)
- No invented allocations for ambiguous multi-SVL cases
- Keep fields blank when unsafe, add flags instead
- Populate valuation date, unit costs, incoming/outgoing values, running value/avg

Implemented audit flags include:

- `ZERO_VALUE_SVL`
- `NEGATIVE_RUNNING_QTY`
- `VAL_LINK_MISSING`
- `MULTI_SVL_AMBIGUOUS`
- `BACKDATED_VALUATION_DATE`

## 6) PDF Layout and Business Readability

The QWeb template was polished for business use:

- Bilingual labels (English/Arabic)
- Grouped columns (Incoming / Outgoing / Balance)
- Header, current stock, movement table, totals, warnings, legend
- Empty-state message for no-movement filters
- Clean numeric formatting and `-` for blank valuation cells

Known environment limitation documented:

- `wkhtmltopdf` missing blocks PDF binary generation; HTML rendering remains valid.

## 7) XLSX Export

XLSX export was implemented through an HTTP controller with `xlsxwriter`:

- Wizard button: **Export XLSX**
- Controller validates stock manager group and wizard ownership
- Reuses `prepare_report_data(wizard)` to mirror PDF content
- Includes same sections: header, stock, rows, totals, warnings, flag legend

## 8) QA and Hardening

Final QA verified:

- Security boundaries and wizard/menu access
- Read-only behavior (no stock/accounting mutations)
- Consistency across PDF/XLSX shared data source
- Scenario coverage including zero-value SVL, negative running qty, no-movement range, valuation hidden filter

## 9) Playwright UI Testing

Playwright automation was added to validate end-to-end UI behavior:

- Login and navigation to wizard
- Scenario-based wizard inputs
- Screenshot capture for each scenario
- XLSX download verification and workbook parsing
- PDF handling that marks wkhtmltopdf failures as environment-blocked (not functional failure)

Evidence output is organized under:

- `tests/artifacts/stock_product_movement_report/`

Module-level screenshot copies are stored in:

- `stock_product_movement_report/src/screenshots/`

## 10) Delivery Outcome

Final delivered module provides:

- Inventory reporting wizard for product movement valuation
- PDF/HTML report layout
- XLSX export
- Shared report service architecture
- Audit flags for valuation traceability
- Automated UI test evidence

The implementation remains aligned with the original requirement:

- **Audit and reporting only**
- **No stock valuation recalculation**
- **No stock/accounting data modification**
