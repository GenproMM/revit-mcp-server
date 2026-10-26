# -*- coding: UTF-8 -*-
"""Bridge-internal open read for confirmation facts (D-09); never a mutation.

Reports what the named mutation would touch. Unknown facts stay unknown; no trial
transaction, file open, document activation or write is performed.
"""

import logging
import os

from pyrevit import routes, DB

from .security import strip_envelope
from .identity import mutation_document_or_response, request_document_selector
from .textutils import parse_request_data
from .utils import make_element_id, get_element_id_value, get_element_name, sanitize_string
from .lookup import (
    resolve_set_parameter, resolve_instance_parameter, shared_definitions_by_name,
    find_family_by_name, parameter_has_value, type_instance_count,
)

logger = logging.getLogger(__name__)

SUPPORTED_ROUTES = (
    "/set_parameter/", "/modify_element/", "/delete_elements/",
    "/transform_elements/", "/edit_family/", "/load_family/",
)


ELEMENT_CAP = 2000
PARAMETER_CAP = 50
SCAN_CAP = 20000


def _unavailable(reason):
    return {"available": False, "reason": reason}


def _bounded(builder):
    """A failed fact read must not masquerade as an exact or partially exact result."""
    def collect(doc, args):
        try:
            return builder(doc, args)
        except Exception as exc:
            logger.warning("Preflight facts unavailable: %s", type(exc).__name__)
            return _unavailable(type(exc).__name__)
    return collect


def _parameter_values(doc, parameter):
    if not parameter.HasValue:
        return "", None
    storage = parameter.StorageType
    if storage == DB.StorageType.String:
        raw = parameter.AsString()
        return sanitize_string(raw or ""), sanitize_string(raw) if raw is not None else None
    if storage == DB.StorageType.Integer:
        raw = parameter.AsInteger()
    elif storage == DB.StorageType.Double:
        raw = parameter.AsDouble()
    elif storage == DB.StorageType.ElementId:
        key = parameter.AsElementId()
        raw = get_element_id_value(key)
        referenced = doc.GetElement(key) if raw != -1 else None
        return get_element_name(referenced) if referenced is not None else "", raw
    else:
        return None, None
    display = parameter.AsValueString()
    return sanitize_string(display) if display else str(raw), raw


def _parameter_facts(doc, args, instance_only=False):
    requested = (args.get("parameters") or {}) if instance_only else {}
    if instance_only and len(requested) > PARAMETER_CAP:
        return _unavailable("too_many_parameters")
    names = list(requested.keys()) if instance_only else [args.get("parameter_name")]
    key = args.get("element_id")
    element = doc.GetElement(make_element_id(key))
    if element is None:
        return {"available": True, "element": {"id": key, "exists": False}, "parameters": []}
    is_type = isinstance(element, DB.ElementType)
    type_element = element if is_type else doc.GetElement(element.GetTypeId())
    family = getattr(type_element, "Family", None) if type_element is not None else None
    category = element.Category
    details = {
        "id": get_element_id_value(element.Id), "exists": True,
        "category": get_element_name(category) if category is not None else None,
        "is_type": is_type,
        "type": get_element_name(type_element) if type_element is not None else None,
        "family": get_element_name(family) if family is not None else None,
        "group_member": get_element_id_value(element.GroupId) != -1,
        "type_instance_count": None, "count_capped": False,
    }
    parameters = []
    touches_type = is_type
    for name in names:
        if instance_only:
            parameter = resolve_instance_parameter(element, name)
            resolved = "instance" if parameter is not None else None
        else:
            parameter, resolved = resolve_set_parameter(doc, element, name)
        touches_type = touches_type or resolved == "type"
        item = {"name": sanitize_string(name), "resolved": resolved or "not_found",
                "read_only": None, "storage_type": None, "has_value": None,
                "display_value": None, "raw_value": None}
        if parameter is not None:
            display, raw = _parameter_values(doc, parameter)
            item.update({"read_only": bool(parameter.IsReadOnly),
                         "storage_type": sanitize_string(str(parameter.StorageType)),
                         "has_value": parameter_has_value(parameter),
                         "display_value": display, "raw_value": raw})
        parameters.append(item)
    if touches_type and type_element is not None:
        details["type_instance_count"], details["count_capped"] = type_instance_count(
            doc, type_element, SCAN_CAP)
    return {"available": True, "element": details, "parameters": parameters}


def _set_parameter(doc, args):
    return _parameter_facts(doc, args)


def _modify_element(doc, args):
    return _parameter_facts(doc, args, instance_only=True)


def _elements(doc, args):
    keys = args.get("element_ids") or []
    if len(keys) > ELEMENT_CAP:
        return _unavailable("too_many_ids")
    categories = {}
    kinds = dict((name, 0) for name in ("type", "parameter_definition", "family", "view", "level"))
    classes = (("type", DB.ElementType), ("parameter_definition", DB.ParameterElement),
               ("family", DB.Family), ("view", DB.View), ("level", DB.Level))
    missing = []
    found = pinned = 0
    for key in keys:
        element = doc.GetElement(make_element_id(key))
        if element is None:
            if len(missing) < 20:
                missing.append(key)
            continue
        found += 1
        pinned += int(bool(element.Pinned))
        category = get_element_name(element.Category) if element.Category is not None else "(none)"
        categories[category] = categories.get(category, 0) + 1
        for name, kind in classes:
            if isinstance(element, kind):
                kinds[name] += 1
    top = sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:10]
    return {"available": True, "requested": len(keys), "found": found, "missing": missing,
            "categories": dict(top), "kinds": kinds, "pinned": pinned, "cascade": "unknown"}


def _transform(doc, args):
    result = _elements(doc, args)
    if result["available"]:
        result["operation"] = args.get("operation")
    return result


def _optional_definition_text(definition, attribute):
    try:
        value = getattr(definition, attribute)()
        return sanitize_string(value.TypeId) if value is not None else None
    except Exception as exc:
        logger.warning("Shared definition metadata unavailable: %s", type(exc).__name__)
        return None


def _shared_facts(doc, names):
    configured = doc.Application.SharedParametersFilename or None
    definitions = shared_definitions_by_name(doc.Application.OpenSharedParameterFile()) if configured else {}
    result = []
    for name in names:
        matches = definitions.get(name, [])
        guids = set(str(item.GUID).lower() for item in matches)
        ambiguous = len(guids) > 1
        item = {"name": sanitize_string(name), "resolved": bool(matches), "guid": None,
                "datatype": None, "group": None, "ambiguous": ambiguous}
        if matches and not ambiguous:
            definition = matches[-1]
            item["guid"] = str(definition.GUID).lower()
            item["datatype"] = _optional_definition_text(definition, "GetDataType")
            group = getattr(definition, "OwnerGroup", None)
            item["group"] = get_element_name(group) if group is not None else None
        result.append(item)
    return {"configured_file": sanitize_string(configured) if configured else None, "definitions": result}


def _family_count(doc, symbol_ids):
    count = scanned = 0
    for element in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        scanned += 1
        if scanned >= SCAN_CAP:
            return None, True
        if get_element_id_value(element.GetTypeId()) in symbol_ids:
            count += 1
    return count, False


def _edit_family(doc, args):
    parameters = args.get("parameters") or {}
    shared_names = args.get("add_shared_parameters") or []
    if len(parameters) + len(shared_names) > PARAMETER_CAP:
        return _unavailable("too_many_parameters")
    name = args.get("family_name")
    family = find_family_by_name(doc, name)
    details = {"name": sanitize_string(name), "found": family is not None, "id": None,
               "editable": None, "in_place": None, "symbol_count": None,
               "instance_count": None, "count_capped": False}
    if family is not None:
        symbols = set()
        for key in family.GetFamilySymbolIds():
            symbols.add(get_element_id_value(key))
            if len(symbols) >= SCAN_CAP:
                return _unavailable("too_many_symbols")
        count, capped = _family_count(doc, symbols)
        details.update({"id": get_element_id_value(family.Id), "editable": bool(family.IsEditable),
                        "in_place": bool(family.IsInPlace), "symbol_count": len(symbols),
                        "instance_count": count, "count_capped": capped})
    return {"available": True, "family": details,
            "requested": {"parameters": [sanitize_string(key) for key in parameters],
                          "type_name": args.get("type_name"), "new_type_name": args.get("new_type_name"),
                          "reload": args.get("reload", True)},
            "shared": _shared_facts(doc, shared_names) if shared_names else {
                "configured_file": None, "definitions": []}}


def _load_family(doc, args):
    path = args.get("file_path")
    exists = os.path.exists(path)
    name = os.path.splitext(os.path.basename(path))[0]
    return {"available": True, "file": {"path": path, "exists": exists,
            "size": os.path.getsize(path) if exists else None}, "family_name": name,
            "already_loaded": find_family_by_name(doc, name) is not None, "contents": "unknown"}


_FACTS = {
    "/set_parameter/": _bounded(_set_parameter),
    "/modify_element/": _bounded(_modify_element),
    "/delete_elements/": _bounded(_elements),
    "/transform_elements/": _bounded(_transform),
    "/edit_family/": _bounded(_edit_family),
    "/load_family/": _bounded(_load_family),
}


def register_preflight_routes(api):
    @api.route("/mutation_preflight/", methods=["POST"])
    def mutation_preflight_handler(uiapp, doc, request):
        """Resolve the document exactly as a mutation does, then read bounded facts."""
        strip_envelope(request)
        try:
            try:
                data = parse_request_data(request.data)
            except Exception:
                return routes.make_response(
                    data={"error": "Invalid preflight body", "error_code": "preflight-bad-request"},
                    status=400)
            if not isinstance(data, dict) or not isinstance(data.get("args", {}), dict):
                return routes.make_response(
                    data={"error": "Preflight body and args must be objects",
                          "error_code": "preflight-bad-request"}, status=400)
            route = data.get("route")
            if route not in SUPPORTED_ROUTES:
                return routes.make_response(
                    data={"error": "Unsupported preflight route",
                          "error_code": "preflight-unsupported-route"}, status=400)
            selected_doc, descriptor, refusal = mutation_document_or_response(
                request_document_selector(request), uiapp=uiapp)
            if refusal is not None:
                return refusal
            facts = _FACTS[route](selected_doc, data.get("args", {}))
            return routes.make_response(data={
                "status": "ok", "route": route, "document": descriptor, "facts": facts,
            }, status=200)
        except Exception as exc:
            logger.warning("Mutation preflight failed: %s", type(exc).__name__)
            return routes.make_response(data={
                "error": "Preflight failed ({})".format(type(exc).__name__),
                "error_code": "preflight-failed",
            }, status=500)
