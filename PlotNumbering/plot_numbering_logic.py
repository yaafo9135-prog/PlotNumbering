# Plot Numbering — QGIS plugin
# Copyright (C) 2026 Hamadu Hudu Yaafo
# This file is part of Plot Numbering.
#
# Plot Numbering is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Plot Numbering is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# LICENSE file for details.

from qgis.PyQt.QtCore import QMetaType
from qgis.core import (
    QgsField,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)
from .numbering_algorithms import sort_features, group_by_block, ORDER_MODES
import re


def available_order_modes():
    return ORDER_MODES


def is_null_value(value):
    if value is None:
        return True
    try:
        from qgis.core import QgsVariantUtils
        if QgsVariantUtils.isNull(value):
            return True
    except Exception:
        pass
    try:
        text = str(value).strip().lower()
    except Exception:
        return True
    return text in ("", "null", "none", "<null>")


def clean_existing_values(values):
    result = set()
    for value in values or []:
        if is_null_value(value):
            continue
        text = str(value).strip()
        if text:
            result.add(text)
    return result


def format_number(n, prefix="", suffix="", padding=0):
    # v1.5 default: NO leading zeros. Padding remains available only when
    # explicitly requested by the user.
    padding = max(0, int(padding))
    number_text = str(int(n)) if padding == 0 else f"{int(n):0{padding}d}"
    return f"{prefix}{number_text}{suffix}"


def generate_numbers(
    features,
    order="north_west",
    start=1,
    prefix="",
    suffix="",
    padding=0,
    skip_existing=False,
    continue_existing=False,
    existing_values=None,
    start_point=None,
    direction_degrees=0,
    block_field=None,
    block_separator="-",
    block_padding=0,
):
    existing_values = clean_existing_values(existing_values)
    next_number = int(start)

    if continue_existing:
        nums = []
        for value in existing_values:
            try:
                if re.fullmatch(r"[+-]?\d+", value):
                    nums.append(int(value))
            except (ValueError, TypeError):
                pass
        if nums:
            next_number = max(nums) + 1

    used = set(existing_values) if skip_existing else set()
    result = {}

    if block_field:
        groups = group_by_block(features, block_field)
        block_items = sorted(groups.items(), key=lambda x: str(x[0]))
        for block_index, (block_value, block_features) in enumerate(block_items, start=1):
            ordered = sort_features(
                block_features, order,
                start_point=start_point,
                direction_degrees=direction_degrees,
            )
            if is_null_value(block_value):
                block_label = str(block_index)
            else:
                raw_block = str(block_value).strip()
                if re.fullmatch(r"\d+", raw_block) and int(block_padding) > 0:
                    block_label = raw_block.zfill(int(block_padding))
                else:
                    block_label = raw_block

            for f in ordered:
                value = format_number(
                    next_number, f"{prefix}{block_label}{block_separator}",
                    suffix, padding
                )
                while value in used:
                    next_number += 1
                    value = format_number(
                        next_number, f"{prefix}{block_label}{block_separator}",
                        suffix, padding
                    )
                result[f.id()] = value
                used.add(value)
                next_number += 1
        return result

    ordered = sort_features(
        features, order,
        start_point=start_point,
        direction_degrees=direction_degrees,
    )
    for f in ordered:
        value = format_number(next_number, prefix, suffix, padding)
        while value in used:
            next_number += 1
            value = format_number(next_number, prefix, suffix, padding)
        result[f.id()] = value
        used.add(value)
        next_number += 1
    return result


def _new_text_field_name(layer, base_name):
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(base_name)).strip("_") or "Plot_No"
    candidate = f"{safe}_TEXT"
    counter = 2
    while candidate in layer.fields().names():
        candidate = f"{safe}_TEXT_{counter}"
        counter += 1
    return candidate


def _generated_values_are_plain_integers(values):
    return all(re.fullmatch(r"[+-]?\d+", str(v).strip()) for v in values)


def _needs_leading_zero_preservation(values):
    for value in values:
        text = str(value).strip().lstrip("+-")
        if len(text) > 1 and text.startswith("0"):
            return True
    return False


def field_can_store_values(field, values):
    """Strictly decide whether a QGIS field can store the generated values."""
    if field is None:
        return False
    generated = [str(v) for v in values.values() if not is_null_value(v)]
    if not generated:
        return False

    if field.isNumeric():
        # Numeric destination is safe only for plain integers with no leading
        # zeros and no prefix/suffix.
        return _generated_values_are_plain_integers(generated) and not _needs_leading_zero_preservation(generated)

    # QGIS String field.
    try:
        is_string = str(field.type()) == str(QMetaType.Type.QString) or str(field.typeName()).lower() in {
            "string", "text", "varchar", "char", "nvarchar"
        }
    except Exception:
        is_string = False
    if not is_string:
        return False

    try:
        max_len = int(field.length())
    except Exception:
        max_len = 0
    required = max(len(v) for v in generated)
    return max_len <= 0 or required <= max_len


def ensure_output_field_before_edit(layer, requested_field, values):
    """Return a compatible output field BEFORE edit mode starts.

    This is intentionally provider-level schema work. Adding a field while a
    Shapefile/OGR layer is already editing can leave the provider with a stale
    field map and cause errors such as 'wrong data type ... QString' at commit.
    """
    if not values or any(is_null_value(v) for v in values.values()):
        raise ValueError("The numbering result contains NULL/empty values. No edits were made.")

    if requested_field and requested_field in layer.fields().names():
        field = layer.fields().field(requested_field)
        if field_can_store_values(field, values):
            return requested_field, False

    base = requested_field or "Plot_No"
    new_name = _new_text_field_name(layer, base)
    generated = [str(v) for v in values.values()]
    required_len = max(64, max(len(v) for v in generated))
    new_field = QgsField(new_name, QMetaType.Type.QString, len=required_len)

    if not layer.dataProvider().addAttributes([new_field]):
        raise RuntimeError(
            f"Could not create compatible text field '{new_name}'. "
            "The data provider rejected the schema change."
        )
    layer.updateFields()
    if new_name not in layer.fields().names():
        raise RuntimeError(f"The new output field '{new_name}' was not added to the layer.")
    return new_name, True


def apply_numbers(layer, field_name, values):
    idx = layer.fields().indexOf(field_name)
    if idx < 0:
        raise ValueError(f"Field not found: {field_name}")
    field = layer.fields().field(idx)
    if field is None:
        raise ValueError(f"Could not read output field: {field_name}")

    for fid, raw_value in values.items():
        if is_null_value(raw_value):
            raise ValueError(f"Refusing to write NULL plot number to feature {fid}.")
        text = str(raw_value).strip()
        if field.isNumeric():
            try:
                value = int(text)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Output field '{field_name}' is numeric but plot number '{text}' is not an integer."
                )
        else:
            value = text

        ok = layer.changeAttributeValue(fid, idx, value)
        if not ok:
            raise RuntimeError(
                f"QGIS rejected plot number '{text}' for feature {fid} in field '{field_name}'."
            )


def set_simple_labels(layer, field_name):
    settings = QgsPalLayerSettings()
    settings.fieldName = field_name
    text_format = QgsTextFormat()
    text_format.setSize(10)
    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
