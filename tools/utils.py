# -*- coding: utf-8 -*-
"""Utility functions for MCP tools"""

import json
import re

# The bridge tags what it returns with provenance metadata under this attribute
# name (dict and str subclasses, never a key in the body). Tools never import the
# transport, so the name is duplicated here; tests/unit/test_identity_rendering.py
# pins the two copies equal.
PROVENANCE_ATTR = "revit_provenance"

_HTTP_ERROR_TEXT = re.compile(r"Error: \d{3} - ")


def format_response(response):
    """Format an API response for an MCP tool and append its provenance.

    This is the one renderer every tool path goes through. The projection of the
    reply (message / result / data / output / error block) is unchanged; the
    attribution is appended after it, so a reply collapsed to its message still
    names what the bridge verified:

    * received: the verified answering Revit process, plus the document the
      ROUTE reports in its reply (never the one that was requested). An
      /execute_code/ reply (it carries ``document_scope``) shows the process and
      the scope notice only, never a document as changed.
    * not sent / no reply / outcome unknown / unverified reply: no process and no
      document is credited; at most the requested target is named.

    A result without bridge provenance (a refusal built inside a tool, or a
    body that merely contains ``process_identity``) is rendered exactly as before.

    Args:
        response: The response from a revit_get or revit_post call, can be dict or string

    Returns:
        str: Formatted string response suitable for MCP tool return values
    """
    text = _project_response(response)
    provenance = getattr(response, PROVENANCE_ATTR, None)
    if not isinstance(provenance, dict):
        return text
    lines = _provenance_lines(response, provenance, text)
    if not lines:
        return text
    return "\n".join([str(text)] + lines)


def _body_of(response):
    """The JSON object of a reply: the dict itself or the body of an HTTP error text."""
    if isinstance(response, dict):
        return response
    if isinstance(response, str):
        match = _HTTP_ERROR_TEXT.match(response)
        if match:
            try:
                body = json.loads(response[match.end():])
            except ValueError:
                return None
            if isinstance(body, dict):
                return body
    return None


def _describe_document(entry):
    title = entry.get("title") or "(untitled)"
    parts = []
    if entry.get("document"):
        parts.append("document {}".format(entry["document"]))
    if "path" in entry:
        parts.append("path: {}".format(entry.get("path") or "(never saved)"))
    if entry.get("active"):
        parts.append("active")
    if entry.get("is_family_document"):
        parts.append("family document")
    return "{} ({})".format(title, "; ".join(parts)) if parts else title


def _document_lines(body):
    """What the route itself reports about the document(s) a call used; [] when it reports none."""
    lines = []
    document = body.get("document")
    if isinstance(document, dict):
        lines.append("Revit reported this document for the call: {}".format(
            _describe_document(document)))
    changed = body.get("documents_changed")
    if isinstance(changed, list) and any(isinstance(e, dict) for e in changed):
        lines.append("Documents this call worked on, as reported by Revit:")
        for entry in changed:
            if not isinstance(entry, dict):
                continue
            extra = "; changed: {}".format("yes" if entry.get("changed") else "no")
            if entry.get("role") == "family":
                extra += "; saved: {}".format("yes" if entry.get("saved") else "no")
            lines.append("- {}: {}{}".format(entry.get("role") or "document",
                                             _describe_document(entry), extra))
    observed = body.get("observed_active_document")
    if isinstance(observed, dict):
        lines.append("Active document re-read by Revit after the call: {}".format(
            _describe_document(observed)))
    return lines


def _requested_phrase(requested):
    """Name the REQUESTED target (never evidence of an answer), or say none was established."""
    if isinstance(requested, dict) and requested.get("address"):
        return "requested target {}, PID {}; not confirmed as the answering process".format(
            requested["address"], requested.get("pid"))
    return "no target was established"


def _provenance_lines(response, provenance, text):
    kind = provenance.get("kind")
    requested = _requested_phrase(provenance.get("requested"))
    if kind == "not-sent":
        return ["Attribution: none. This request was not sent to Revit, so no Revit process or "
                "document is credited with it ({}).".format(requested)]
    if kind == "unknown":
        return ["Attribution: unconfirmed. The request was sent toward Revit ({}) but no complete "
                "trustworthy reply was accepted, so its outcome is UNKNOWN and no Revit process "
                "or document is confirmed to have handled it.".format(requested)]
    if kind == "no-reply":
        return ["Attribution: none. No reply was accepted, so no Revit process or document is "
                "credited with this read ({}).".format(requested)]
    if kind == "unverified-reply":
        return ["Attribution: unconfirmed. A reply (HTTP {}) arrived but the answering process "
                "could not be verified, so no Revit process or document is credited with "
                "it ({}).".format(provenance.get("http_status"), requested)]
    if kind != "received":
        return []
    lines = []
    body = _body_of(response)
    if body is not None:
        notice = body.get("document_scope")
        if notice:
            # D-15: arbitrary code reports no used document; never render one as changed.
            if str(notice) not in str(text):
                lines.append("Document scope: {}".format(notice))
        else:
            lines.extend(_document_lines(body))
    process = provenance.get("process")
    if isinstance(process, dict):
        lines.append("Verified Revit process: PID {}; Revit {}; port {}; session {}".format(
            process.get("pid"), process.get("revit_version"), process.get("actual_port"),
            process.get("session_token")))
    return lines


def _project_response(response):
    """The projection of one reply to text, unchanged since before provenance rendering.

    A dict is an error only if it has a truthy "error" key or a status in
    error/failed/failure/exception; every other dict is data. Do not add new
    implicit error signals here.
    """
    if isinstance(response, dict):
        if "_verified_process" in response:
            # Reserved bridge metadata key: never part of the projected payload.
            response = dict((k, v) for k, v in response.items() if k != "_verified_process")
        # Check for different success patterns
        status = response.get("status", "").lower()
        health = response.get("health", "").lower()

        # Routes signal failure with an "error" key or an explicit failure status.
        # Any other dict (including data-bearing responses that omit "status",
        # e.g. get_revit_model_info) is a success — otherwise good data is
        # mislabeled as an error.
        has_error = (bool(response.get("error")) or
                     status in ("error", "failed", "failure", "exception"))
        is_success = not has_error

        if is_success:
            # For successful responses, return the most relevant data
            if "output" in response:  # Code execution responses
                return response["output"]
            elif "message" in response:
                return response["message"]
            elif "result" in response:
                return str(response["result"])
            elif "data" in response:
                return str(response["data"])
            elif status == "active":  # Status check responses
                # Format status response nicely
                status_parts = ["=== REVIT STATUS ==="]
                status_parts.append("Status: {}".format(response.get("status", "Unknown")))
                status_parts.append("Health: {}".format(response.get("health", "Unknown")))
                
                if "api_name" in response:
                    status_parts.append("API: {}".format(response["api_name"]))
                if "document_title" in response:
                    status_parts.append("Document: {}".format(response["document_title"]))
                if "revit_available" in response:
                    status_parts.append("Revit Available: {}".format(response["revit_available"]))
                
                # Add any other fields that might be present
                known_fields = {"status", "health", "api_name", "document_title", "revit_available"}
                other_fields = set(response.keys()) - known_fields
                if other_fields:
                    status_parts.append("")
                    for field in sorted(other_fields):
                        status_parts.append("{}: {}".format(field.replace("_", " ").title(), response[field]))
                
                return "\n".join(status_parts)
            else:
                # Structured success payload without a standard wrapper key
                # (e.g. model info, level lists). Surface the data instead of
                # hiding it behind a generic message.
                data_fields = dict((k, v) for k, v in response.items()
                                   if k not in ("status", "health", "success"))
                if data_fields:
                    parts = []
                    for key in sorted(data_fields):
                        parts.append("{}: {}".format(key.replace("_", " ").title(),
                                                      data_fields[key]))
                    return "\n".join(parts)
                return "Operation completed successfully"
        else:
            # Error case - provide verbose debugging information
            error_msg = response.get("error", "Unknown error occurred")
            traceback_info = response.get("traceback", "")
            details = response.get("details", "")
            status = response.get("status", "unknown")
            
            # Build comprehensive error message
            error_parts = ["=== ERROR DETAILS ==="]
            error_parts.append("Status: {}".format(status))
            error_parts.append("Error: {}".format(error_msg))
            
            if details:
                error_parts.append("Details: {}".format(details))
            
            if traceback_info:  # Code execution error with traceback
                error_parts.append("\n=== TRACEBACK ===")
                error_parts.append(traceback_info)
            
            # Add any additional fields that might be helpful for debugging
            debug_fields = ["code_attempted", "endpoint", "request_data", "response_code"]
            for field in debug_fields:
                if field in response:
                    error_parts.append("{}: {}".format(field.replace("_", " ").title(), response[field]))
            
            # Include full response for debugging if it has unexpected fields
            response_keys = set(response.keys()) - {"error", "traceback", "details", "status", "code_attempted", "endpoint", "request_data", "response_code"}
            if response_keys:
                error_parts.append("\n=== ADDITIONAL RESPONSE DATA ===")
                for key in sorted(response_keys):
                    error_parts.append("{}: {}".format(key, response[key]))
            
            return "\n".join(error_parts)
    else:
        # If response is already a string (error case from _revit_call)
        return str(response)


# Deliberately duplicated from revit_mcp/textutils.py. The two halves of this
# repo never share an interpreter, so tools/ cannot import from revit_mcp/;
# see the Two-Runtime Rule in CLAUDE.md. Keep the two copies in step.
_ESCAPE_CULPRITS = {
    "\x07": "\\a",
    "\x08": "\\b",
    "\x0c": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\x0b": "\\v",
    "\0": "\\0",
}


def describe_broken_path(path: str):
    """Return a diagnosis if `path` carries mangled escapes, else None.

    A Windows path typed into a non-raw string literal loses every backslash
    that forms a recognised escape, so "C:\10_bim\new.rvt" arrives carrying a
    backspace and a newline. No legal Windows path contains a control
    character, which makes their presence unambiguous evidence.

    A Cyrillic path makes this look like an encoding fault, which it is not:
    non-ASCII survives the bridge intact because json.dumps escapes it to
    \\uXXXX and json.loads restores it.
    """
    if not isinstance(path, str):
        return None

    hits = []
    for index, char in enumerate(path):
        code = ord(char)
        if code < 32 or code == 127:
            culprit = _ESCAPE_CULPRITS.get(char, "\\x{:02x}".format(code))
            hits.append("U+{:04X} at position {} (from a literal {})".format(
                code, index, culprit))
    if not hits:
        return None

    return (
        "The path contains control characters, which means its backslashes were "
        "consumed as escape sequences before it arrived: {}. Resend the path with "
        "doubled backslashes (\"G:\\\\folder\\\\file.rvt\"), as a raw string "
        "(r\"G:\\folder\\file.rvt\"), or with forward slashes (\"G:/folder/file.rvt\"). "
        "This is not a Unicode problem: Cyrillic and other non-ASCII path names "
        "transfer correctly.".format("; ".join(hits))
    )
