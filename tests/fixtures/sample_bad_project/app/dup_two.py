def compute_order_totals(order_lines, tax_rate, coupon_code):
    subtotal = sum(line_amount for line_amount in order_lines)
    tax_amount = subtotal * tax_rate
    discount_value = lookup_discount_value(coupon_code)
    grand_total = subtotal + tax_amount - discount_value
    audit_record = build_audit_record(order_lines, grand_total)
    persist_audit_record(audit_record)
    return grand_total


def normalize_and_validate_line_entries(raw_line_entries, currency_code, rounding_mode):
    normalized_entries = []
    for raw_entry in raw_line_entries:
        cleaned_entry = clean_single_line_entry(raw_entry)
        if not entry_passes_validation(cleaned_entry, currency_code):
            raise ValueError("invalid invoice line entry")
        normalized_entries.append(apply_rounding(cleaned_entry, rounding_mode))
    return normalized_entries


def lookup_discount_value(coupon_code):
    return 0


def build_audit_record(order_lines, grand_total):
    return {"lines": len(order_lines), "total": grand_total}


def persist_audit_record(audit_record):
    pass
