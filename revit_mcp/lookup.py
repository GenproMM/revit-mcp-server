# -*- coding: UTF-8 -*-
"""Shared Revit lookup helpers for mutation routes and mutation preflight (D-09).

This helper registers no routes. Keeping the parameter, family and count resolution in
one place makes the confirmation preflight report the same Revit objects the mutation
will touch.
"""

from pyrevit import DB

from .utils import get_element_name, get_element_id_value


def _db():
    """The current pyRevit DB namespace; test worlds replace it between route imports."""
    from pyrevit import DB as current_db
    return current_db


def resolve_set_parameter(doc, element, name):
    """Return (parameter, level) using the set_parameter instance-then-type order."""
    parameter = resolve_instance_parameter(element, name)
    if parameter is not None:
        return parameter, "instance"
    try:
        type_id = element.GetTypeId()
        if type_id is None or type_id == _db().ElementId.InvalidElementId:
            return None, None
        element_type = doc.GetElement(type_id)
        parameter = resolve_instance_parameter(element_type, name)
        if parameter is not None:
            return parameter, "type"
    except Exception:
        pass
    return None, None


def resolve_instance_parameter(element, name):
    """The instance-only LookupParameter resolution used by modify_element."""
    try:
        return element.LookupParameter(name) if element is not None else None
    except Exception:
        return None


def shared_definitions_by_name(shared_file):
    """Definitions grouped by name in file order; duplicate names remain observable."""
    result = {}
    if shared_file is None:
        return result
    try:
        groups = shared_file.Groups
    except Exception:
        return result
    try:
        for group in groups:
            try:
                definitions = group.Definitions
            except Exception:
                continue
            for definition in definitions:
                try:
                    name = definition.Name
                except Exception:
                    continue
                result.setdefault(name, []).append(definition)
    except Exception:
        pass
    return result


def find_family_by_name(doc, name):
    """The first loaded Family whose sanitized Revit name equals ``name``."""
    try:
        db = _db()
        families = db.FilteredElementCollector(doc).OfClass(db.Family).ToElements()
        for family in families:
            if get_element_name(family) == name:
                return family
    except Exception:
        pass
    return None


def parameter_has_value(parameter):
    """Whether a parameter holds a meaningful value, or None when it cannot be read."""
    try:
        if parameter is None or not parameter.HasValue:
            return False
        if parameter.StorageType == _db().StorageType.String:
            return bool(parameter.AsString())
        return True
    except Exception:
        return None


def type_instance_count(doc, type_element, cap):
    """Count instances of a type up to ``cap``; (None, True) means the cap was reached."""
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
        for element in collector:
            try:
                if get_element_id_value(element.GetTypeId()) != get_element_id_value(type_element.Id):
                    continue
            except Exception:
                continue
            count += 1
            if count >= cap:
                return None, True
        return count, False
    except Exception:
        return None, False
