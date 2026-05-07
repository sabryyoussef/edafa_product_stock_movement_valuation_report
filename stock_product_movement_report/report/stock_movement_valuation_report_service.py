from odoo import models


class StockMovementValuationReportService(models.AbstractModel):
    _name = "stock.movement.valuation.report.service"
    _description = "Stock Movement Valuation Report Service"

    def _build_scope(self, wizard):
        wizard.ensure_one()
        location_model = self.env["stock.location"].with_context(active_test=False)
        company = wizard.company_id
        include_child = bool(wizard.include_child_locations)

        if wizard.location_id:
            if include_child:
                locations = location_model.search(
                    [
                        ("id", "child_of", wizard.location_id.id),
                        ("usage", "=", "internal"),
                        ("company_id", "in", [company.id, False]),
                    ]
                )
            else:
                locations = wizard.location_id.filtered(
                    lambda loc: loc.usage == "internal"
                    and (not loc.company_id or loc.company_id == company)
                )
        elif wizard.warehouse_id:
            root_location = wizard.warehouse_id.lot_stock_id
            locations = location_model.search(
                [
                    ("id", "child_of", root_location.id),
                    ("usage", "=", "internal"),
                    ("company_id", "in", [company.id, False]),
                ]
            )
        else:
            locations = location_model.search(
                [
                    ("usage", "=", "internal"),
                    ("company_id", "in", [company.id, False]),
                ]
            )

        return {
            "product": wizard.product_id,
            "company": company,
            "date_from": wizard.date_from,
            "date_to": wizard.date_to,
            "warehouse": wizard.warehouse_id,
            "location": wizard.location_id,
            "location_ids": locations.ids,
            "include_child_locations": include_child,
            "show_internal_transfers": bool(wizard.show_internal_transfers),
            "show_valuation": bool(wizard.show_valuation),
        }

    def _line_qty(self, move_line):
        if "quantity" in move_line._fields:
            return move_line.quantity
        return move_line.qty_done

    def _movement_datetime(self, move_line):
        return move_line.date or move_line.move_id.date or move_line.picking_id.date_done

    def _svl_date(self, svl):
        return svl.create_date if "create_date" in svl._fields else False

    def _compute_line_direction(self, move_line, location_ids_set, show_internal_transfers):
        src_in_scope = move_line.location_id.id in location_ids_set
        dest_in_scope = move_line.location_dest_id.id in location_ids_set
        qty = self._line_qty(move_line)

        if src_in_scope and not dest_in_scope:
            return {
                "include": True,
                "incoming_qty": "",
                "outgoing_qty": qty,
                "delta_qty": -qty,
                "src_in_scope": src_in_scope,
                "dest_in_scope": dest_in_scope,
            }
        if dest_in_scope and not src_in_scope:
            return {
                "include": True,
                "incoming_qty": qty,
                "outgoing_qty": "",
                "delta_qty": qty,
                "src_in_scope": src_in_scope,
                "dest_in_scope": dest_in_scope,
            }
        if src_in_scope and dest_in_scope:
            return {
                "include": bool(show_internal_transfers),
                "incoming_qty": "",
                "outgoing_qty": "",
                "delta_qty": 0.0,
                "src_in_scope": src_in_scope,
                "dest_in_scope": dest_in_scope,
            }
        return {
            "include": False,
            "incoming_qty": "",
            "outgoing_qty": "",
            "delta_qty": 0.0,
            "src_in_scope": src_in_scope,
            "dest_in_scope": dest_in_scope,
        }

    def _classify_movement(self, move_line, delta_qty, src_in_scope, dest_in_scope):
        move = move_line.move_id
        src_usage = move_line.location_id.usage
        dest_usage = move_line.location_dest_id.usage

        if move.origin_returned_move_id:
            if delta_qty > 0:
                return "Return Incoming"
            if delta_qty < 0:
                return "Return Outgoing"
            return "Other"

        if move_line.location_dest_id.scrap_location:
            return "Scrap"
        if src_usage == "supplier" and dest_in_scope:
            return "Incoming"
        if src_in_scope and dest_usage == "customer":
            return "Outgoing"
        if src_usage == "inventory" and dest_in_scope:
            return "Inventory Adjustment"
        if src_in_scope and dest_usage == "inventory":
            return "Inventory Adjustment"
        if src_usage == "production" and dest_in_scope:
            return "Manufacturing In"
        if src_in_scope and dest_usage == "production":
            return "Manufacturing Consumption"
        if src_in_scope and dest_in_scope:
            return "Internal Transfer"
        if delta_qty > 0:
            return "Incoming"
        if delta_qty < 0:
            return "Outgoing"
        return "Other"

    def _line_origin(self, move_line):
        return move_line.move_id.origin or move_line.picking_id.origin or ""

    def _line_document_ref(self, move_line):
        return (
            move_line.picking_id.name
            or move_line.move_id.reference
            or move_line.move_id.name
            or ""
        )

    def _line_move_ref(self, move_line):
        return move_line.move_id.reference or move_line.move_id.name or ""

    def _get_valuation_map(self, move_ids, scope):
        svl_model = self.env["stock.valuation.layer"]
        required_fields = ["stock_move_id", "quantity", "value", "unit_cost", "create_date"]
        missing_required = [name for name in required_fields if name not in svl_model._fields]
        has_lot = "lot_id" in svl_model._fields

        valuation_map = {
            "svls_by_move_id": {},
            "svls_by_move_lot": {},
            "has_lot": has_lot,
            "warnings": [],
            "enabled": not missing_required,
        }
        if missing_required:
            valuation_map["warnings"].append(
                "SVL fields missing in this environment: %s" % ", ".join(missing_required)
            )
            return valuation_map
        if not move_ids:
            return valuation_map

        domain = [("stock_move_id", "in", list(move_ids))]
        if "company_id" in svl_model._fields:
            domain.append(("company_id", "=", scope["company"].id))
        svls = svl_model.search(domain, order="create_date asc, id asc")

        by_move = {}
        by_move_lot = {}
        for svl in svls:
            move_id = svl.stock_move_id.id
            by_move.setdefault(move_id, []).append(svl)
            if has_lot and svl.lot_id:
                by_move_lot.setdefault((move_id, svl.lot_id.id), []).append(svl)
        valuation_map["svls_by_move_id"] = by_move
        valuation_map["svls_by_move_lot"] = by_move_lot
        return valuation_map

    def _resolve_line_valuation(self, move_line, valuation_map):
        result = {
            "svl": False,
            "valuation_date": "",
            "unit_cost": "",
            "value_abs": "",
            "flags": [],
        }
        if not valuation_map.get("enabled"):
            result["flags"].append("VAL_LINK_MISSING")
            return result

        move_id = move_line.move_id.id
        candidates = valuation_map["svls_by_move_id"].get(move_id, [])
        if not candidates:
            result["flags"].append("VAL_LINK_MISSING")
            return result

        selected = False
        if move_line.lot_id and valuation_map.get("has_lot"):
            lot_matches = valuation_map["svls_by_move_lot"].get((move_id, move_line.lot_id.id), [])
            if len(lot_matches) == 1:
                selected = lot_matches[0]
            elif len(lot_matches) > 1:
                result["flags"].append("MULTI_SVL_AMBIGUOUS")
                return result

        if not selected:
            if len(candidates) == 1:
                selected = candidates[0]
            else:
                result["flags"].append("MULTI_SVL_AMBIGUOUS")
                return result

        quantity = selected.quantity
        value = selected.value
        unit_cost = selected.unit_cost
        if not unit_cost and quantity:
            unit_cost = abs(value) / abs(quantity)

        result.update(
            {
                "svl": selected,
                "valuation_date": self._svl_date(selected) or "",
                "unit_cost": unit_cost if unit_cost else "",
                "value_abs": abs(value) if value is not False else "",
            }
        )
        return result

    def _is_backdated(self, movement_dt, valuation_dt):
        if not movement_dt or not valuation_dt:
            return False
        return movement_dt.date() != valuation_dt.date()

    def _scoped_line_infos(self, scope, date_domain):
        move_line_model = self.env["stock.move.line"]
        domain = self._base_move_line_domain(scope) + date_domain
        move_lines = move_line_model.search(domain, order="date asc, id asc")
        location_ids_set = set(scope["location_ids"])
        infos = []
        for move_line in move_lines:
            direction = self._compute_line_direction(
                move_line,
                location_ids_set,
                scope["show_internal_transfers"],
            )
            if not direction["include"]:
                continue
            infos.append(
                {
                    "move_line": move_line,
                    "direction": direction,
                    "movement_dt": self._movement_datetime(move_line),
                }
            )
        return infos

    def _prepare_current_stock(self, scope):
        quant_model = self.env["stock.quant"]
        domain = [
            ("product_id", "=", scope["product"].id),
            ("company_id", "=", scope["company"].id),
            ("location_id", "in", scope["location_ids"]),
        ]
        grouped = quant_model.read_group(
            domain,
            ["quantity:sum"],
            ["location_id"],
            lazy=False,
        )
        current_stock = []
        total_qty = 0.0
        for item in grouped:
            location_name = item.get("location_id") and item["location_id"][1] or ""
            qty = item.get("quantity", 0.0) or 0.0
            total_qty += qty
            current_stock.append(
                {
                    "location": location_name,
                    "qty": qty,
                    "value": "",
                }
            )
        return current_stock, total_qty

    def _base_move_line_domain(self, scope):
        return [
            ("product_id", "=", scope["product"].id),
            ("company_id", "=", scope["company"].id),
            ("move_id.state", "=", "done"),
            "|",
            ("location_id", "in", scope["location_ids"]),
            ("location_dest_id", "in", scope["location_ids"]),
        ]

    def _compute_opening_qty(self, opening_infos):
        opening_qty = 0.0
        for info in opening_infos:
            opening_qty += info["direction"]["delta_qty"]
        return opening_qty

    def _compute_opening_value(self, scope, opening_infos, valuation_map):
        if not scope["show_valuation"]:
            return "", "", []

        opening_value = 0.0
        opening_flags = []
        partial = False
        for info in opening_infos:
            delta_qty = info["direction"]["delta_qty"]
            if not delta_qty:
                continue
            valuation = self._resolve_line_valuation(info["move_line"], valuation_map)
            if valuation["flags"] or valuation["value_abs"] == "":
                partial = True
                continue
            if delta_qty > 0:
                opening_value += valuation["value_abs"]
            else:
                opening_value -= valuation["value_abs"]
        if partial:
            opening_flags.append("OPENING_VALUATION_PARTIAL")
        opening_avg = ""
        opening_qty = self._compute_opening_qty(opening_infos)
        if opening_qty and isinstance(opening_value, (int, float)):
            opening_avg = opening_value / opening_qty
        return opening_value, opening_avg, opening_flags

    def _prepare_rows(self, scope, opening_qty, opening_value, valuation_map):
        in_range_infos = self._scoped_line_infos(
            scope,
            [("date", ">=", scope["date_from"]), ("date", "<=", scope["date_to"])],
        )

        rows = []
        incoming_total = 0.0
        outgoing_total = 0.0
        incoming_value_total = 0.0
        outgoing_value_total = 0.0
        running_qty = opening_qty
        running_value = opening_value if isinstance(opening_value, (int, float)) else 0.0
        valuation_partial = False
        negative_running_qty = opening_qty < 0
        if not isinstance(opening_value, (int, float)):
            valuation_partial = True

        for info in in_range_infos:
            move_line = info["move_line"]
            direction = info["direction"]

            running_qty += direction["delta_qty"]
            movement_type = self._classify_movement(
                move_line,
                direction["delta_qty"],
                direction["src_in_scope"],
                direction["dest_in_scope"],
            )
            movement_dt = info["movement_dt"]
            incoming_qty = direction["incoming_qty"]
            outgoing_qty = direction["outgoing_qty"]
            if isinstance(incoming_qty, (int, float)):
                incoming_total += incoming_qty
            if isinstance(outgoing_qty, (int, float)):
                outgoing_total += outgoing_qty

            notes = []
            valuation_date = ""
            incoming_unit_cost = ""
            incoming_value = ""
            outgoing_unit_cost = ""
            outgoing_value = ""
            running_avg_cost = ""
            delta_value = None

            if scope["show_valuation"]:
                if movement_type == "Internal Transfer":
                    if valuation_map["svls_by_move_id"].get(move_line.move_id.id):
                        notes.append("INTERNAL_TRANSFER_VALUATION_IGNORED")
                else:
                    valuation = self._resolve_line_valuation(move_line, valuation_map)
                    notes.extend(valuation["flags"])
                    if not valuation["flags"] and valuation["value_abs"] != "":
                        valuation_date = valuation["valuation_date"] or ""
                        if direction["delta_qty"] and valuation["value_abs"] == 0:
                            notes.append("ZERO_VALUE_SVL")
                        if direction["delta_qty"] > 0:
                            incoming_unit_cost = valuation["unit_cost"]
                            incoming_value = valuation["value_abs"]
                            incoming_value_total += valuation["value_abs"]
                            delta_value = valuation["value_abs"]
                        elif direction["delta_qty"] < 0:
                            outgoing_unit_cost = valuation["unit_cost"]
                            outgoing_value = valuation["value_abs"]
                            outgoing_value_total += valuation["value_abs"]
                            delta_value = -valuation["value_abs"]
                        if self._is_backdated(movement_dt, valuation_date):
                            notes.append("BACKDATED_VALUATION_DATE")
                    elif direction["delta_qty"]:
                        valuation_partial = True
            else:
                notes = []

            if isinstance(delta_value, (int, float)):
                running_value += delta_value
                if running_qty:
                    running_avg_cost = running_value / running_qty
            elif scope["show_valuation"] and direction["delta_qty"]:
                valuation_partial = True

            if running_qty < 0:
                notes.append("NEGATIVE_RUNNING_QTY")
                negative_running_qty = True

            rows.append(
                {
                    "movement_date": movement_dt or "",
                    "valuation_date": valuation_date,
                    "document_ref": self._line_document_ref(move_line),
                    "origin": self._line_origin(move_line),
                    "move_ref": self._line_move_ref(move_line),
                    "product": scope["product"].display_name,
                    "lot": move_line.lot_id.name or "",
                    "expiry_date": move_line.expiration_date or move_line.lot_id.expiration_date or "",
                    "source_location": move_line.location_id.display_name,
                    "dest_location": move_line.location_dest_id.display_name,
                    "movement_type": movement_type,
                    "incoming_qty": incoming_qty,
                    "incoming_unit_cost": incoming_unit_cost,
                    "incoming_value": incoming_value,
                    "outgoing_qty": outgoing_qty,
                    "outgoing_unit_cost": outgoing_unit_cost,
                    "outgoing_value": outgoing_value,
                    "running_qty": running_qty,
                    "running_avg_cost": running_avg_cost,
                    "running_value": running_value if scope["show_valuation"] else "",
                    "notes": ", ".join(sorted(set(notes))),
                }
            )
        return {
            "rows": rows,
            "incoming_total": incoming_total,
            "outgoing_total": outgoing_total,
            "incoming_value_total": incoming_value_total if scope["show_valuation"] else "",
            "outgoing_value_total": outgoing_value_total if scope["show_valuation"] else "",
            "ending_qty": running_qty,
            "ending_value": running_value if scope["show_valuation"] else "",
            "valuation_partial": valuation_partial,
            "negative_running_qty": negative_running_qty,
        }

    def prepare_report_data(self, wizard):
        wizard.ensure_one()
        scope = self._build_scope(wizard)
        product = scope["product"]
        product_template = product.product_tmpl_id
        warehouse_name = scope["warehouse"].display_name if scope["warehouse"] else ""
        location_name = scope["location"].display_name if scope["location"] else ""

        opening_infos = self._scoped_line_infos(scope, [("date", "<", scope["date_from"])])
        opening_qty = self._compute_opening_qty(opening_infos)
        all_move_ids = {info["move_line"].move_id.id for info in opening_infos}
        in_range_infos = self._scoped_line_infos(
            scope, [("date", ">=", scope["date_from"]), ("date", "<=", scope["date_to"])]
        )
        all_move_ids.update({info["move_line"].move_id.id for info in in_range_infos})
        valuation_map = self._get_valuation_map(all_move_ids, scope) if scope["show_valuation"] else {}
        opening_value = ""
        opening_avg_cost = ""
        opening_flags = []
        if scope["show_valuation"]:
            opening_value, opening_avg_cost, opening_flags = self._compute_opening_value(
                scope, opening_infos, valuation_map
            )
        row_data = self._prepare_rows(scope, opening_qty, opening_value, valuation_map)
        current_stock, current_total_qty = self._prepare_current_stock(scope)
        warnings = [
            "This report is audit/read-only and does not recalculate stock valuation.",
            "Current stock value by location is intentionally blank in this step.",
            "Running balances are calculated within the selected date/location scope.",
        ]
        if not scope["show_valuation"]:
            warnings.append("Valuation hidden by filter.")
        else:
            warnings.extend(valuation_map.get("warnings", []))
            warnings.append(
                "Zero-value valuation layers may indicate zero-cost, manual valuation, or non-valued configuration."
            )
            if opening_flags:
                warnings.extend(opening_flags)
            if row_data["valuation_partial"]:
                warnings.append(
                    "Running value may be partial where valuation links are missing or ambiguous."
                )
                warnings.append("VALUATION_PARTIAL")
        if row_data["negative_running_qty"]:
            warnings.append("NEGATIVE_RUNNING_QTY")
        if not row_data["rows"]:
            warnings.append("No movements found for selected filters.")

        return {
            "header": {
                "company_name": scope["company"].display_name,
                "product_name": product.display_name,
                "product_code": product.default_code or "",
                "uom": product.uom_id.display_name or "",
                "cost_method": product_template.cost_method or "",
                "date_from": str(scope["date_from"] or ""),
                "date_to": str(scope["date_to"] or ""),
                "warehouse": warehouse_name,
                "location": location_name,
                "show_valuation": scope["show_valuation"],
            },
            "current_stock": current_stock,
            "opening": {
                "qty": opening_qty,
                "avg_cost": opening_avg_cost if scope["show_valuation"] else "",
                "value": opening_value if scope["show_valuation"] else "",
            },
            "rows": row_data["rows"],
            "totals": {
                "incoming_qty": row_data["incoming_total"],
                "incoming_value": row_data["incoming_value_total"],
                "outgoing_qty": row_data["outgoing_total"],
                "outgoing_value": row_data["outgoing_value_total"],
                "ending_qty": row_data["ending_qty"] if row_data["rows"] else opening_qty,
                "ending_value": row_data["ending_value"] if row_data["rows"] else opening_value,
                "current_total_qty": current_total_qty,
            },
            "warnings": warnings,
        }
