# -*- coding: UTF-8 -*-
"""Shared Revit lookup helpers for mutation routes and mutation preflight (D-09).

This helper registers no routes. Keeping the parameter, family and count resolution in
one place makes the confirmation preflight report the same Revit objects the mutation
will touch.
"""

import logging

from .utils import get_element_name, get_element_id_value

logger = logging.getLogger(__name__)


def _db():
    """Resolve the active pyRevit DB namespace when a helper needs API types."""
    from pyrevit import DB as current_db
    return current_db


def resolve_set_parameter(doc, element, name):
    """Return (parameter, level) using the set_parameter instance-then-type order."""
    parameter = resolve_instance_parameter(element, name)
    if parameter is not None:
        return parameter, "instance"
    if element is None:
        return None, None
    type_id = element.GetTypeId()
    if type_id is None or type_id == _db().ElementId.InvalidElementId:
        return None, None
    element_type = doc.GetElement(type_id)
    parameter = resolve_instance_parameter(element_type, name)
    if parameter is not None:
        return parameter, "type"
    return None, None


def resolve_instance_parameter(element, name):
    """The instance-only LookupParameter resolution used by modify_element."""
    return element.LookupParameter(name) if element is not None else None


def shared_definitions_by_name(shared_file):
    """Definitions grouped by name in file order; duplicate names remain observable."""
    result = {}
    if shared_file is None:
        return result
    for group in shared_file.Groups:
        for definition in group.Definitions:
            result.setdefault(definition.Name, []).append(definition)
    return result


def find_family_by_name(doc, name):
    """The first loaded Family whose sanitized Revit name equals ``name``."""
    db = _db()
    families = db.FilteredElementCollector(doc).OfClass(db.Family).ToElements()
    for family in families:
        if get_element_name(family) == name:
            return family
    return None


def parameter_has_value(parameter):
    """Whether a parameter holds a meaningful value, or None when it cannot be read."""
    try:
        if parameter is None or not parameter.HasValue:
            return False
        if parameter.StorageType == _db().StorageType.String:
            return bool(parameter.AsString())
        return True
    except Exception as exc:
        logger.warning("Parameter value unavailable: %s", type(exc).__name__)
        return None


def type_instance_count(doc, type_element, cap):
    """Count type instances scanning at most ``cap`` elements; capped counts are unknown."""
    try:
        db = _db()
        if getattr(type_element, "Family", None) is not None:
            collector = db.FilteredElementCollector(doc).WherePasses(
                db.FamilyInstanceFilter(doc, type_element.Id))
        else:
            category = getattr(type_element, "Category", None)
            collector = db.FilteredElementCollector(doc)
            if category is not None:
                collector = collector.OfCategoryId(category.Id)
            collector = collector.WhereElementIsNotElementType()
        count = 0
        scanned = 0
        for element in collector:
            scanned += 1
            if scanned >= cap:
                return None, True
            if get_element_id_value(element.GetTypeId()) == get_element_id_value(type_element.Id):
                count += 1
        return count, False
    except Exception as exc:
        logger.warning("Type instance count unavailable: %s", type(exc).__name__)
        return None, False
