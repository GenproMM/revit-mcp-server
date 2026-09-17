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
from .textutils import sanitize_string, describe_broken_path
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
    """
    True for a Revit Server user-visible path (RSN://...).

    The backslash spelling counts too, and so does a single separator after the
    colon: users paste these out of Revit and Windows dialogs, and escaping on
    the way in varies. Misreading one as a local path means os.path.exists()
    decides the model is missing. Kept in step with the same-named helper in
    tools/worksharing_tools.py.
    """
    if not file_path:
        return False
    return str(file_path).strip().lower().replace("\\", "/").startswith("rsn:/")


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


def _default_local_dir():
    """Revit's own default home for local copies: the user's Documents folder."""
    return os.path.join(os.path.expanduser("~"), "Documents")


def _local_copy_name(file_path, suffix):
    """
    Build the local file name Revit's own "Create New Local" would use:
    <central name>_<user>.rvt.
    """
    base = os.path.basename(str(file_path).replace("\\", "/").rstrip("/"))
    if base.lower().endswith(".rvt"):
        base = base[:-4]
    return "{}_{}.rvt".format(base, suffix)


def _current_user(app):
    """Revit's logged-in username, falling back to the OS user."""
    try:
        name = sanitize_string(app.Username)
        if name:
            return name
    except Exception:
        logger.warning("Application.Username unavailable; using the OS user")
    return os.environ.get("USERNAME") or os.environ.get("USER") or "local"


def _make_local_copy(model_path, file_path, app, local_path=None, overwrite=True):
    """
    Create a local copy of a central model and return (local ModelPath, report).

    This is the API equivalent of the "Create New Local" checkbox in Revit's
    Open dialog. Without it, opening a central without detaching edits the
    central file itself, which is exactly what corrupts a workshared model --
    and on Revit Server it is not even a file Revit can write back to.
    """
    if not local_path:
        local_path = os.path.join(
            _default_local_dir(),
            _local_copy_name(file_path, _current_user(app)),
        )
    local_path = os.path.abspath(local_path)

    parent = os.path.dirname(local_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except Exception as e:
            return None, {"error": "Could not create {}: {}".format(parent, str(e))}

    existed = os.path.exists(local_path)
    if existed and not overwrite:
        return None, {
            "error": ("A local copy already exists at {}. Pass overwrite_local=true "
                      "to replace it, or local_path to write elsewhere.").format(
                          local_path)
        }

    # CreateNewLocal refuses to write over an existing file, so an overwrite
    # has to remove it first. Any unsynchronised work in that copy is lost --
    # which is why overwrite_local=false exists.
    if existed:
        try:
            os.remove(local_path)
        except Exception as e:
            return None, {
                "error": ("Could not replace the existing local copy at {}: {}. "
                          "It is most likely open in Revit.").format(local_path, str(e))
            }

    local_model_path = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(local_path)
    try:
        DB.WorksharingUtils.CreateNewLocal(model_path, local_model_path)
    except Exception as e:
        return None, {
            "error": "Could not create a local copy at {}: {}".format(
                local_path, str(e))
        }
    return local_model_path, {
        "local_path": local_path,
        "replaced_existing_local": bool(existed),
    }


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
                # A path mangled by backslash escapes is by far the most common
                # cause here, and a bare "not found" sends people hunting for a
                # Unicode bug that does not exist. Say which it is.
                problem = describe_broken_path(file_path)
                error = "Model not found: {}".format(file_path)
                if problem:
                    error = "{} -- {}".format(error, problem)
                return routes.make_response(
                    data={"error": error},
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
            "audit": false,
            "local_path": null,
            "overwrite_local": true
        }

        detach is preserve | discard | none; "preserve" is the Revit dialog
        option "Detach and preserve worksets" and is the default. A
        non-workshared file is opened with neither detach nor workset
        configuration, because Revit rejects both on such a file.

        detach="none" on a central model creates a local copy first
        (WorksharingUtils.CreateNewLocal, the API form of the Open dialog's
        "Create New Local" checkbox) and opens that copy. Opening a central
        directly is what corrupts workshared models, and a Revit Server
        central cannot be opened in place at all.
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
                # A path mangled by backslash escapes is by far the most common
                # cause here, and a bare "not found" sends people hunting for a
                # Unicode bug that does not exist. Say which it is.
                problem = describe_broken_path(file_path)
                error = "Model not found: {}".format(file_path)
                if problem:
                    error = "{} -- {}".format(error, problem)
                return routes.make_response(
                    data={"error": error},
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
            local_path = data.get("local_path")
            overwrite_local = bool(data.get("overwrite_local", True))

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

            # Opening without detaching means working on the model for real, so
            # it has to happen on a local copy -- never on the central itself.
            local_report = None
            open_path = model_path
            if is_workshared and detach == "none":
                is_central = file_info["is_central"]
                # BasicFileInfo reports None on some versions; a Revit Server
                # path is always a central, and for a file-based model a local
                # copy is harmless even when the flag is unknown.
                if is_central is None or is_central or _is_revit_server_path(file_path):
                    local_model_path, local_report = _make_local_copy(
                        model_path, file_path, app,
                        local_path=local_path, overwrite=overwrite_local,
                    )
                    if local_model_path is None:
                        return routes.make_response(
                            data={
                                "error": local_report["error"],
                                "file_path": file_path,
                                "requested_detach": detach,
                            },
                            status=500,
                        )
                    open_path = local_model_path
                    logger.info("Opening local copy {} of {}".format(
                        local_report["local_path"], file_path))

            opened = None
            was_activated = False
            try:
                if activate:
                    uidoc = host.uiapp.OpenAndActivateDocument(open_path, options, False)
                    opened = uidoc.Document if uidoc else None
                    was_activated = True
                else:
                    opened = app.OpenDocumentFile(open_path, options)
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
                "is_local_copy": local_report is not None,
            }
            if local_report:
                result["local_path"] = local_report["local_path"]
                result["replaced_existing_local"] = local_report[
                    "replaced_existing_local"]
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
