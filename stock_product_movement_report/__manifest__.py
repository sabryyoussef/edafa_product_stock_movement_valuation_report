{
    "name": "Product Stock Movement Valuation Report",
    "version": "18.0.1.0.0",
    "summary": "Wizard-driven product movement valuation PDF report",
    "category": "Inventory/Reporting",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_account",
        "product_expiry",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_movement_valuation_report_wizard_views.xml",
        "report_xml/stock_movement_valuation_report.xml",
    ],
    "application": False,
    "installable": True,
}
