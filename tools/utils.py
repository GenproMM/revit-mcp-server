# -*- coding: utf-8 -*-
"""Utility functions for MCP tools"""


def format_response(response):
    """Helper function to format API responses consistently for MCP tools.

    Args:
        response: The response from a revit_get or revit_post call, can be dict or string

    Returns:
        str: Formatted string response suitable for MCP tool return values
    """
    if isinstance(response, dict):
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
