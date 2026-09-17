# -*- coding: utf-8 -*-
from pyrevit import DB
import traceback
import logging

# sanitize_string / normalize_string live in textutils so they can be imported
# and unit tested under CPython 3 (this module cannot -- it needs pyRevit).
# Re-exported here so route modules keep using `from utils import ...`.
from .textutils import (  # noqa: F401
    normalize_string,
    parse_request_data,
    sanitize_string,
    sanitize_value,
)

logger = logging.getLogger(__name__)


class _FailureSwallower(DB.IFailuresPreprocessor):
    """Resolve Revit failures during a transaction without ever showing a modal
    dialog. Warnings are deleted (the operation proceeds); if any error-severity
    failure is present, the transaction is rolled back. Either way the headless
    Routes server keeps running instead of hanging on a dialog.

    Every failure message is logged, and any rollback verdict is recorded on
    `self.rolled_back` / `self.failures` so the caller (suppress_warnings'
    transaction owner) can surface it instead of reporting a false success.
    Previously this rollback was completely silent: a route would call
    t.Commit(), get back TransactionStatus.RolledBack, discard that return
    value, and still answer {"status": "success"} to the client while the
    edit vanished from the model. See debug session param-write-rolls-back.
    """

    def __init__(self):
        self.rolled_back = False
        self.failures = []

    def PreprocessFailures(self, failuresAccessor):
        try:
            # Delete all warnings so they don't block (operation continues).
            failuresAccessor.DeleteAllWarnings()
            # If any genuine errors remain, roll back rather than go modal.
            has_error = False
            for f in failuresAccessor.GetFailureMessages():
                try:
                    severity = f.GetSeverity()
                    description = f.GetDescriptionText()
                except Exception:
                    severity = None
                    description = "<failure text unavailable>"
                is_error = severity == DB.FailureSeverity.Error
                if is_error:
                    has_error = True
                failing_ids = []
                try:
                    for fid in f.GetFailingElements():
                        failing_ids.append(get_element_id_value(fid))
                except Exception:
                    pass
                entry = {
                    "severity": str(severity),
                    "description": description,
                    "failing_element_ids": failing_ids,
                }
                self.failures.append(entry)
                log_fn = logger.error if is_error else logger.warning
                log_fn(
                    "Transaction failure (severity=%s): %s (elements=%s)",
                    entry["severity"], description, failing_ids,
                )
            if has_error:
                self.rolled_back = True
                logger.error(
                    "Transaction rolled back due to %d error-severity failure(s).",
                    sum(1 for x in self.failures if x["severity"] == str(DB.FailureSeverity.Error)),
                )
                return DB.FailureProcessingResult.ProceedWithRollBack
        except Exception:
            logger.exception("_FailureSwallower.PreprocessFailures itself raised")
        return DB.FailureProcessingResult.Continue


def suppress_warnings(transaction):
    """Configure a transaction so Revit failures never block on a modal dialog.

    Essential for unattended/headless operation: without this, a routine Revit
    warning (e.g. overlapping walls) OR an error (e.g. "Can't cut instance out
    of Wall") pops a modal dialog that blocks the Routes server indefinitely —
    every later request then times out until a human clicks the dialog.

    Warnings are auto-deleted (operation proceeds); errors roll the transaction
    back cleanly. Call right after transaction.Start(). Best-effort — never raises.

    Returns the `_FailureSwallower` instance so the caller can inspect
    `.rolled_back` / `.failures` after `transaction.Commit()`, alongside the
    Commit() return value itself. Returns None if setup failed (best-effort) --
    callers should still check the TransactionStatus from Commit() in that case.
    """
    try:
        swallower = _FailureSwallower()
        opts = transaction.GetFailureHandlingOptions()
        opts.SetForcedModalHandling(False)
        opts.SetClearAfterRollback(True)
        opts.SetFailuresPreprocessor(swallower)
        transaction.SetFailureHandlingOptions(opts)
        return swallower
    except Exception:
        logger.exception("suppress_warnings failed to install failure handling options")
        return None


def commit_and_report(transaction, swallower=None):
    """Commit `transaction` and return a dict describing what really happened.

    Never trust a route's own "status": "success" after calling
    transaction.Commit() without checking this. Commit() returns a
    TransactionStatus that silently comes back RolledBack when
    _FailureSwallower vetoes the transaction -- discarding that return value
    (the previous behavior in code_execution.py, parameters.py and
    editing.py) makes a rollback indistinguishable from a real commit.

    Returns:
        {
            "committed": bool,               # True only if status == Committed
            "transaction_status": str,        # str(TransactionStatus)
            "failures": [ {severity, description, failing_element_ids}, ... ],
        }
    """
    status = transaction.Commit()
    failures = list(swallower.failures) if swallower is not None else []
    return {
        "committed": status == DB.TransactionStatus.Committed,
        "transaction_status": str(status),
        "failures": failures,
    }


def get_element_name(element):
    """
    Get the name of a Revit element.
    Useful for both FamilySymbol and other elements.
    Returns a JSON-safe unicode string (non-ASCII characters preserved).
    """
    try:
        name = element.Name
    except AttributeError:
        name = DB.Element.Name.__get__(element)
    return sanitize_string(name)


def get_element_id_value(element_or_id):
    """
    Extract an integer element ID from an Element or ElementId.
    Accepts both a full Revit Element and a raw ElementId (duck typing).
    Compatible with Revit 2024, 2025, 2026, and 2027.
    Returns a plain Python int for JSON serialization.
    Raises ValueError if the ID cannot be extracted or input is None.
    """
    if element_or_id is None:
        raise ValueError("Cannot extract ElementId from None")
    try:
        eid = element_or_id.Id if hasattr(element_or_id, "Id") else element_or_id
    except Exception:
        raise ValueError("Cannot extract ElementId from input: {}".format(
            type(element_or_id).__name__))
    try:
        return int(eid.Value)
    except (AttributeError, TypeError):
        pass
    try:
        return int(eid.IntegerValue)
    except (AttributeError, TypeError):
        raise ValueError("Cannot read ID value from: {}".format(
            type(element_or_id).__name__))


def make_element_id(id_value):
    """
    Create a DB.ElementId from an integer value.
    Compatible with Revit 2024, 2025, 2026, and 2027.
    Tries System.Int64 constructor first (2024+), falls back to int.
    Raises ValueError if the ElementId cannot be created or input is invalid.
    """
    if id_value is None:
        raise ValueError("Cannot create ElementId from None")
    try:
        int_val = int(id_value)
    except (TypeError, ValueError):
        raise ValueError("Cannot create ElementId from {}: not a valid integer".format(
            repr(id_value)))
    try:
        import System
        return DB.ElementId(System.Int64(int_val))
    except (TypeError, OverflowError, ImportError):
        pass
    try:
        return DB.ElementId(int_val)
    except Exception as e:
        raise ValueError("Cannot create ElementId from {}: {}".format(
            id_value, str(e)))


def find_family_symbol_safely(doc, target_family_name, target_type_name=None):
    """
    Safely find a family symbol by name.
    Uses get_element_name() for consistent string handling in IronPython.
    """
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)

        for symbol in collector:
            try:
                fam_name = sanitize_string(symbol.Family.Name)
            except Exception:
                continue
            if fam_name == target_family_name:
                if not target_type_name or get_element_name(symbol) == target_type_name:
                    return symbol
        return None
    except Exception as e:
        logger.error("Error finding family symbol: %s", str(e))
        return None
