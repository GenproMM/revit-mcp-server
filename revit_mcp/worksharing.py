# -*- coding: UTF-8 -*-
"""
Worksharing Module for Revit MCP
Opening workshared models with detach + selective workset configuration.

Note: OpenDocumentFile / OpenAndActivateDocument must NOT run inside a
Transaction, so these handlers deliberately do not open one. This is also why
/execute_code/ cannot open a model: it wraps the snippet in a transaction and
never exposes the Application.

The workset configuration is applied on every open path. Without it Revit pulls
each attached RVT link in as its own document — on a large federated model that
is roughly ten extra discipline models and ten times the memory.
"""

from pyrevit import routes, DB
from .utils import parse_request_data
from .textutils import sanitize_string
import os
import logging

logger = logging.getLogger(__name__)

# Central/workshared models open detached with all user worksets closed by
# default. The sentinel is handled by _matches_any and is not a workset name.
DEFAULT_LINK_WORKSET_PATTERNS = ["__ALL_USER_WORKSETS__"]

# "preserve" is the Revit dialog option "Detach and preserve worksets".
_DETACH_MODES = {
    "preserve": "DetachAndPreserveWorksets",
    "discard": "DetachAndDiscardWorksets",
    "none": "DoNotDetach",
}


def _get_host_app():
    """Return pyRevit HOST_APP, which carries .app (Application) and .uiapp."""
    from pyrevit import HOST_APP
    return HOST_APP


def _matches_any(name, patterns):
    """True when name contains any of patterns, case-insensitively."""
    if "__ALL_USER_WORKSETS__" in patterns:
        return True
    upper = (name or "").upper()
    for pattern in patterns:
        if pattern and pattern.upper() in upper:
            return True
    return False


def _is_revit_server_path(file_path):
    """True for a Revit Server user-visible path (RSN://...)."""
    return bool(file_path) and str(file_path).strip().lower().startswith("rsn://")


def _to_model_path(file_path):
    """Convert a local or Revit Server user-visible path to ModelPath."""
    return DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(file_path)


def _model_exists(file_path, model_path):
    """Check local files on disk and RSN models through Revit's API."""
    if not _is_revit_server_path(file_path):
        return os.path.exists(file_path)
    # RSN models are remote and therefore never satisfy os.path.exists().
    # The actual Revit API calls below validate the ModelPath and return the
    # useful server/open error when the model cannot be resolved.
    return True


def _extract_file_info(file_path, model_path=None):
    """
    Read a .rvt header without opening the file. Values are None when Revit
    cannot report them.
    """
    result = {"is_workshared": None, "is_central": None, "saved_in_version": None}
    try:
        if model_path is None:
            model_path = _to_model_path(file_path)
        info = DB.BasicFileInfo.Extract(model_path)
        if info is None:
            return result
        try:
            result["is_workshared"] = bool(info.IsWorkshared)
        except Exception:
            logger.warning("BasicFileInfo.IsWorkshared unavailable")
        try:
            result["is_central"] = bool(info.IsCentral)
        except Exception:
            logger.warning("BasicFileInfo.IsCentral unavailable")
        try:
            result["saved_in_version"] = sanitize_string(info.SavedInVersion)
        except Exception:
            logger.warning("BasicFileInfo.SavedInVersion unavailable")
    except Exception as e:
        logger.warning(
            "BasicFileInfo.Extract failed for {}: {}".format(file_path, str(e))
        )
    return result


def _workset_infos(model_path):
    """
    Raw WorksharingUtils workset previews for a model on disk.
    Returns (infos, error_message).
    """
    try:
        return list(DB.WorksharingUtils.GetUserWorksetInfo(model_path)), None
    except Exception as e:
        return None, str(e)


def _preview_worksets(model_path):
    """
    List a model's user worksets without opening it.
    Returns (worksets, error) with worksets as [{"id": int, "name": str}].
    """
    infos, error = _workset_infos(model_path)
    if error:
        return None, error

    worksets = []
    for info in infos:
        try:
            worksets.append({
                "id": info.Id.IntegerValue,
                "name": sanitize_string(info.Name),
            })
        except Exception as e:
            logger.warning("Skipping unreadable workset: {}".format(str(e)))
            continue
    return worksets, None


def _build_workset_config(model_path, close_patterns):
    """
    Build a WorksetConfiguration opening everything except worksets matching
    close_patterns. Returns (config, report, error).

    CloseAllWorksets is deliberately not used: a closed workset is invisible to
    FilteredElementCollector, and the configuration applies only once at open
    time, so there is no way to open one later without reopening the model.
    """
    infos, error = _workset_infos(model_path)
    if error:
        return None, None, error

    config = DB.WorksetConfiguration(DB.WorksetConfigurationOption.OpenAllWorksets)

    import System
    id_list = System.Collections.Generic.List[DB.WorksetId]()
    closed_names = []
    opened_names = []

    for info in infos:
        try:
            name = sanitize_string(info.Name)
        except Exception as e:
            logger.warning("Skipping unreadable workset: {}".format(str(e)))
            continue
        if _matches_any(name, close_patterns):
            id_list.Add(info.Id)
            closed_names.append(name)
        else:
            opened_names.append(name)

    if id_list.Count:
        config.Close(id_list)

    report = {
        "worksets_total": len(closed_names) + len(opened_names),
        "worksets_closed": closed_names,
        "worksets_opened": opened_names,
        "close_patterns": list(close_patterns),
    }
    return config, report, None


def register_worksharing_routes(api):
    """Register worksharing / model-open routes with the API."""

    @api.route("/model_worksets/", methods=["POST"])
    def model_worksets(doc, request):
        """
        Preview a model's worksets without opening it. Read-only.

        Payload: {
            "file_path": "C:\\\\path\\\\to\\\\Model.rvt",
            "close_worksets_matching": ["#_RVT_LINK"]
        }
        """
        try:
            data = {}
            if request and request.data:
                data = parse_request_data(request.data)

            file_path = data.get("file_path")
            if not file_path:
                return routes.make_response(
                    data={"error": "file_path is required (full path to a .rvt file)"},
                    status=400,
                )
            model_path = _to_model_path(file_path)
            if not _model_exists(file_path, model_path):
                return routes.make_response(
                    data={"error": "Model not found: {}".format(file_path)},
                    status=404,
                )

            patterns = data.get("close_worksets_matching")
            if patterns is None:
                patterns = DEFAULT_LINK_WORKSET_PATTERNS

            file_info = _extract_file_info(file_path, model_path)
            worksets, error = _preview_worksets(model_path)

            if error:
                return routes.make_response(data={
                    "status": "success",
                    "file_path": file_path,
                    "is_workshared": file_info["is_workshared"],
                    "is_central": file_info["is_central"],
                    "saved_in_version": file_info["saved_in_version"],
                    "workset_count": 0,
                    "worksets": [],
                    "message": "No worksets could be read (the model is most likely "
                               "not workshared): {}".format(error),
                })

            would_close = [
                w["name"] for w in worksets if _matches_any(w["name"], patterns)
            ]
            return routes.make_response(data={
                "status": "success",
                "file_path": file_path,
                "is_workshared": file_info["is_workshared"],
                "is_central": file_info["is_central"],
                "saved_in_version": file_info["saved_in_version"],
                "workset_count": len(worksets),
                "worksets": worksets,
                "would_close": would_close,
                "close_patterns": list(patterns),
            })

        except Exception as e:
            logger.error("model_worksets failed: {}".format(str(e)))
            return routes.make_response(data={"error": str(e)}, status=500)

    @api.route("/open_model/", methods=["POST"])
    def open_model(doc, request):
        """
        Open a model from disk, detaching from central and configuring worksets.

        Payload: {
            "file_path": "C:\\\\path\\\\to\\\\Model.rvt",
            "detach": "preserve",
            "close_worksets_matching": ["#_RVT_LINK"],
            "activate": true,
            "audit": false
        }

        detach is preserve | discard | none; "preserve" is the Revit dialog
        option "Detach and preserve worksets" and is the default. A
        non-workshared file is opened with neither detach nor workset
        configuration, because Revit rejects both on such a file.
        """
        try:
            data = {}
            if request and request.data:
                data = parse_request_data(request.data)

            file_path = data.get("file_path")
            if not file_path:
                return routes.make_response(
                    data={"error": "file_path is required (full path to a .rvt file)"},
                    status=400,
                )
            model_path = _to_model_path(file_path)
            if not _model_exists(file_path, model_path):
                return routes.make_response(
                    data={"error": "Model not found: {}".format(file_path)},
                    status=404,
                )

            detach = str(data.get("detach", "preserve")).lower()
            if detach not in _DETACH_MODES:
                return routes.make_response(
                    data={"error": "detach must be one of: {}".format(
                        ", ".join(sorted(_DETACH_MODES)))},
                    status=400,
                )

            patterns = data.get("close_worksets_matching")
            if patterns is None:
                patterns = DEFAULT_LINK_WORKSET_PATTERNS
            activate = bool(data.get("activate", True))
            audit = bool(data.get("audit", False))

            host = _get_host_app()
            app = host.app
            if app is None:
                return routes.make_response(
                    data={"error": "Revit Application unavailable"}, status=503
                )

            file_info = _extract_file_info(file_path, model_path)

            options = DB.OpenOptions()
            if audit:
                options.Audit = True

            workset_report = None
            applied_detach = "none"

            # Detach and workset configuration are legal only on a workshared
            # file. GetUserWorksetInfo is the authority here: BasicFileInfo
            # reports None for these flags on some Revit versions.
            worksets_probe, probe_error = _workset_infos(model_path)
            is_workshared = probe_error is None and bool(worksets_probe)

            if is_workshared:
                config, workset_report, cfg_error = _build_workset_config(
                    model_path, patterns
                )
                if cfg_error:
                    return routes.make_response(
                        data={"error": "Could not build workset configuration: {}".format(
                            cfg_error)},
                        status=500,
                    )
                options.SetOpenWorksetsConfiguration(config)
                if detach != "none":
                    options.DetachFromCentralOption = getattr(
                        DB.DetachFromCentralOption, _DETACH_MODES[detach]
                    )
                    applied_detach = detach
            elif detach != "none":
                logger.warning(
                    "{} is not workshared; ignoring detach={}".format(file_path, detach)
                )

            opened = None
            was_activated = False
            try:
                if activate:
                    uidoc = host.uiapp.OpenAndActivateDocument(model_path, options, False)
                    opened = uidoc.Document if uidoc else None
                    was_activated = True
                else:
                    opened = app.OpenDocumentFile(model_path, options)
            except Exception as oe:
                return routes.make_response(
                    data={
                        "error": "Open failed: {}".format(str(oe)),
                        "file_path": file_path,
                        "requested_detach": detach,
                        "is_workshared": is_workshared,
                    },
                    status=500,
                )

            if opened is None:
                return routes.make_response(
                    data={"error": "Revit returned no document for {}".format(file_path)},
                    status=500,
                )

            title = ""
            try:
                title = sanitize_string(opened.Title)
            except Exception:
                logger.warning("Could not read the opened document title")

            result = {
                "status": "success",
                "file_path": file_path,
                "document_title": title,
                "detach": applied_detach,
                "requested_detach": detach,
                "is_workshared": is_workshared,
                "is_central": file_info["is_central"],
                "saved_in_version": file_info["saved_in_version"],
                "activated": was_activated,
                "audited": audit,
            }
            if workset_report:
                result.update(workset_report)
            else:
                result["worksets_total"] = 0
                result["message"] = ("The model is not workshared; opened without "
                                     "detach or workset configuration.")
            return routes.make_response(data=result)

        except Exception as e:
            logger.error("open_model failed: {}".format(str(e)))
            return routes.make_response(data={"error": str(e)}, status=500)

    logger.info("Worksharing routes registered successfully")
