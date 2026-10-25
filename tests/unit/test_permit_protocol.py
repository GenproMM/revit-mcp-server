# -*- coding: utf-8 -*-
"""Phase 7 (07-05): the one-time permit protocol, proven on both runtimes.

The CPython minter (permit.py) and the IronPython-dialect verifier (revit_mcp/permits.py)
must agree byte for byte: the hand-rolled HMAC equals the standard one, the MAC of a fixed
golden input is pinned as a literal, every tampering, replay, expiry, wrong-process and
malformed form is refused by name, the edge forms of the wire text verify, and the
refusal body the gate returns carries the mixed-rollout hint (D-19). Needs no Revit.
"""

import hashlib
import hmac
import json

import pytest

import permit
from revit_mcp import permits, trust

SECRET = "phase7-permit-golden-secret-0123456789"
SESSION = "11111111-1111-4111-8111-111111111111"
OTHER_SESSION = "22222222-2222-4222-8222-222222222222"
ROUTE = "/delete_elements/"
POLICY_HASH = "abcdefabcdef"
NOW = 1900000000

GOLDEN_ARGS_TEXT = '{"element_ids":[101,102]}'
GOLDEN_E = 2000000000
GOLDEN_NONCE = "00112233445566778899aabbccddeeff"
# Computed once with stdlib hmac over the seven-line message and pasted here on purpose:
# a literal, so a change to either half's message or key derivation fails this file.
GOLDEN_MAC = "f854249a8c90adc3f47893c7441829909af4709293920050a2181189d1f098c7"

ALL_VERDICTS = (
    permits.OK, permits.MISSING, permits.MALFORMED, permits.UNSUPPORTED, permits.BAD_SIGNATURE,
    permits.ROUTE_MISMATCH, permits.SESSION_MISMATCH, permits.ARGS_MISMATCH, permits.EXPIRED,
    permits.TTL_TOO_LONG, permits.REPLAYED, permits.REGISTRY_FULL, permits.NOT_CONFIGURED,
)


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    monkeypatch.setattr(permits, "_CONSUMED", {})


def mint(args=None, route=ROUTE, session=SESSION, secret=SECRET, ttl=60, now=NOW, nonce=None):
    """(argument text, permit dict) for one fresh permit."""
    text = permit.args_text({"element_ids": [101, 102]} if args is None else args)
    return text, permit.mint(secret, route, text, session, POLICY_HASH, ttl, now=now, nonce=nonce)


def wire(text, minted, secret=SECRET):
    """The exact request bytes the bridge would send."""
    return permit.wire_text(text, {"secret": secret, "permit": minted}).encode("ascii")


def check(raw, route=ROUTE, secret=SECRET, session=SESSION, now=NOW):
    return permits.check_and_consume(raw, route, secret, session, now=now)


# ---- HMAC and key derivation parity (D-18) --------------------------------------------

RFC4231 = (
    ("tc1", b"\x0b" * 20, b"Hi There",
     "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
    ("tc2", b"Jefe", b"what do ya want for nothing?",
     "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
    ("tc6", b"\xaa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First",
     "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
)


@pytest.mark.parametrize("name,key,message,expected", RFC4231, ids=[r[0] for r in RFC4231])
def test_hand_rolled_hmac_matches_rfc_4231_and_the_standard_library(name, key, message, expected):
    digest = permits.hmac_sha256(key, message)
    assert digest.hex() == expected
    assert digest == hmac.new(key, message, hashlib.sha256).digest()


@pytest.mark.parametrize("key,message", [
    (b"k", b""),
    (b"", b"message under an empty key"),
    (b"\x00" * 64, b"key exactly one block"),
    (b"\xff" * 65, b"key one byte over a block"),
], ids=["empty_message", "empty_key", "block_key", "over_block_key"])
def test_hand_rolled_hmac_matches_the_standard_library_on_edge_sizes(key, message):
    assert permits.hmac_sha256(key, message) == hmac.new(key, message, hashlib.sha256).digest()


@pytest.mark.parametrize("secret", [SECRET, "short", "Секрет-кириллица-0123456789", "x" * 131],
                         ids=["golden", "short", "cyrillic", "long"])
def test_derived_keys_are_equal_on_both_sides(secret):
    assert permits.derive_key(secret) == permit.derive_key(secret)
    assert permits.derive_key(secret.encode("utf-8")) == permit.derive_key(secret)


# ---- golden vector --------------------------------------------------------------------

def test_the_minter_reproduces_the_pinned_golden_mac():
    minted = permit.mint(SECRET, ROUTE, GOLDEN_ARGS_TEXT, SESSION, POLICY_HASH, ttl_s=60,
                         now=GOLDEN_E - 60, nonce=GOLDEN_NONCE)
    assert minted["m"] == GOLDEN_MAC
    assert minted["e"] == GOLDEN_E
    assert minted["a"] == hashlib.sha256(GOLDEN_ARGS_TEXT.encode("ascii")).hexdigest()


def test_the_verifier_recomputes_the_same_golden_mac():
    a = hashlib.sha256(GOLDEN_ARGS_TEXT.encode("ascii")).hexdigest()
    message = "\n".join((permits.MAC_PREFIX, ROUTE, a, SESSION, str(GOLDEN_E), GOLDEN_NONCE,
                         POLICY_HASH)).encode("ascii")
    assert permits.hmac_sha256(permits.derive_key(SECRET), message).hex() == GOLDEN_MAC


def test_the_golden_permit_is_accepted_by_the_verifier_once():
    minted = permit.mint(SECRET, ROUTE, GOLDEN_ARGS_TEXT, SESSION, POLICY_HASH, ttl_s=60,
                         now=GOLDEN_E - 60, nonce=GOLDEN_NONCE)
    raw = wire(GOLDEN_ARGS_TEXT, minted)
    assert check(raw, now=GOLDEN_E - 60) == permits.OK
    assert check(raw, now=GOLDEN_E - 60) == permits.REPLAYED


# ---- the accepting path ---------------------------------------------------------------

def test_a_fresh_permit_is_accepted_once_and_then_reported_replayed():
    text, minted = mint()
    raw = wire(text, minted)
    assert check(raw) == permits.OK
    assert check(raw) == permits.REPLAYED
    assert check(raw) == permits.REPLAYED


def test_two_permits_with_different_nonces_for_the_same_text_are_both_accepted():
    text, first = mint()
    _, second = mint()
    assert first["n"] != second["n"]
    assert check(wire(text, first)) == permits.OK
    assert check(wire(text, second)) == permits.OK


def test_the_route_is_compared_after_normalisation():
    text, minted = mint()
    assert check(wire(text, minted), route="delete_elements") == permits.OK
    text, minted = mint()
    assert check(wire(text, minted), route="/delete_elements/?x=1") == permits.OK


# ---- bindings: args, route, session ---------------------------------------------------

def test_one_changed_character_in_the_arguments_is_args_mismatch():
    text, minted = mint()
    tampered = text.replace("101", "102")
    assert tampered != text
    assert check(wire(tampered, minted)) == permits.ARGS_MISMATCH


def test_an_extra_argument_member_is_args_mismatch():
    text, minted = mint()
    assert check(wire('{"element_ids":[101,102],"x":1}', minted)) == permits.ARGS_MISMATCH


def test_a_permit_for_one_route_is_refused_on_another():
    text, minted = mint()
    assert check(wire(text, minted), route="/transform_elements/") == permits.ROUTE_MISMATCH


def test_a_permit_for_one_process_is_refused_by_another():
    text, minted = mint()
    assert check(wire(text, minted), session=OTHER_SESSION) == permits.SESSION_MISMATCH


def test_a_mismatch_does_not_burn_the_permit():
    text, minted = mint()
    raw = wire(text, minted)
    assert check(raw, route="/transform_elements/") == permits.ROUTE_MISMATCH
    assert check(raw, session=OTHER_SESSION) == permits.SESSION_MISMATCH
    assert check(wire(text.replace("101", "102"), minted)) == permits.ARGS_MISMATCH
    assert check(raw) == permits.OK


# ---- expiry ---------------------------------------------------------------------------

def test_a_permit_inside_the_skew_window_is_still_accepted():
    text, minted = mint()
    assert check(wire(text, minted), now=minted["e"] + permits.SKEW) == permits.OK


def test_a_permit_one_second_past_the_skew_window_is_expired():
    text, minted = mint()
    assert check(wire(text, minted), now=minted["e"] + permits.SKEW + 1) == permits.EXPIRED


def test_a_permit_that_expires_too_far_ahead_is_ttl_too_long():
    text, minted = mint()
    assert check(wire(text, minted), now=minted["e"] - permits.MAX_TTL - 1) == permits.TTL_TOO_LONG


def test_a_permit_exactly_max_ttl_ahead_is_accepted():
    text, minted = mint()
    assert check(wire(text, minted), now=minted["e"] - permits.MAX_TTL) == permits.OK


def test_a_permit_minted_with_a_long_ttl_is_refused_even_when_signed_correctly():
    text, minted = mint(ttl=permits.MAX_TTL + 1)
    assert check(wire(text, minted)) == permits.TTL_TOO_LONG


# ---- signature ------------------------------------------------------------------------

def test_one_flipped_hex_digit_of_the_mac_is_bad_signature():
    text, minted = mint()
    digit = minted["m"][0]
    minted["m"] = ("0" if digit != "0" else "1") + minted["m"][1:]
    assert check(wire(text, minted)) == permits.BAD_SIGNATURE


def test_a_permit_minted_under_another_secret_is_bad_signature():
    text, minted = mint(secret="a-different-shared-secret-0123456789")
    assert check(wire(text, minted)) == permits.BAD_SIGNATURE


def test_a_truncated_mac_is_bad_signature():
    text, minted = mint()
    minted["m"] = minted["m"][:-2]
    assert check(wire(text, minted)) == permits.BAD_SIGNATURE


@pytest.mark.parametrize("field,value", [
    ("r", "/transform_elements/"),
    ("s", OTHER_SESSION),
    ("p", "000000000000"),
    ("n", "ffeeddccbbaa99887766554433221100"),
], ids=["route", "session", "policy", "nonce"])
def test_a_field_changed_without_a_new_mac_is_bad_signature(field, value):
    # The signature is checked before the route and session, so an edited field cannot
    # turn a mismatch verdict into acceptance either.
    text, minted = mint()
    minted[field] = value
    route = value if field == "r" else ROUTE
    session = value if field == "s" else SESSION
    assert check(wire(text, minted), route=route, session=session) == permits.BAD_SIGNATURE


def test_an_edited_expiry_without_a_new_mac_is_bad_signature():
    text, minted = mint()
    minted["e"] = minted["e"] + 3600
    assert check(wire(text, minted), now=NOW) == permits.BAD_SIGNATURE


def test_an_edited_argument_hash_is_bad_signature():
    text, minted = mint()
    minted["a"] = hashlib.sha256(b'{"element_ids":[7]}').hexdigest()
    assert check(wire('{"element_ids":[7]}', minted)) == permits.BAD_SIGNATURE


def test_a_bad_signature_does_not_burn_the_nonce():
    text, minted = mint()
    good = dict(minted)
    minted["m"] = "0" * 64
    assert check(wire(text, minted)) == permits.BAD_SIGNATURE
    assert check(wire(text, good)) == permits.OK


# ---- version and shape ----------------------------------------------------------------

def test_an_unsupported_version_is_named():
    text, minted = mint()
    minted["v"] = 2
    assert check(wire(text, minted)) == permits.UNSUPPORTED


def _without(minted, name):
    return dict((k, v) for k, v in minted.items() if k != name)


@pytest.mark.parametrize("make_bad", [
    lambda m: _without(m, "n"),
    lambda m: dict(m, x="extra"),
    lambda m: dict(m, e=str(m["e"])),
    lambda m: dict(m, e=True),
    lambda m: dict(m, v=True),
    lambda m: dict(m, n=7),
    lambda m: dict(m, r="/a/\n/b/"),
    lambda m: "a string, not an object",
    lambda m: [m],
    lambda m: None,
], ids=["no_nonce", "extra_field", "expiry_as_text", "expiry_bool", "version_bool",
        "nonce_int", "newline_in_field", "permit_string", "permit_list", "permit_null"])
def test_a_permit_of_the_wrong_shape_is_malformed(make_bad):
    text, minted = mint()
    envelope = {"secret": SECRET, "permit": make_bad(minted)}
    raw = permit.wire_text(text, envelope).encode("ascii")
    assert check(raw) == permits.MALFORMED


# ---- wire forms -----------------------------------------------------------------------

def test_arguments_before_the_envelope_are_malformed():
    text, minted = mint()
    envelope = json.dumps({"secret": SECRET, "permit": minted}, separators=(",", ":"))
    raw = (text[:-1] + ',"_mcp":' + envelope + "}").encode("ascii")
    assert check(raw) == permits.MALFORMED


def test_two_reserved_members_are_malformed():
    text, minted = mint()
    first = json.dumps({"secret": SECRET, "permit": minted}, separators=(",", ":"))
    second = json.dumps({"secret": "other", "permit": minted}, separators=(",", ":"))
    raw = ('{"_mcp":' + first + ',"_mcp":' + second + "," + text[1:]).encode("ascii")
    assert check(raw) == permits.MALFORMED


def test_raw_utf8_bytes_in_the_body_are_malformed():
    minted = permit.mint(SECRET, ROUTE, '{"name":"x"}', SESSION, POLICY_HASH, 60, now=NOW)
    envelope = json.dumps({"secret": SECRET, "permit": minted}, separators=(",", ":"))
    raw = ('{"_mcp":' + envelope + ',"name":"Стена"}').encode("utf-8")
    assert check(raw) == permits.MALFORMED


def test_a_dict_body_cannot_be_verified_and_is_malformed():
    text, minted = mint()
    body = {"_mcp": {"secret": SECRET, "permit": minted}, "element_ids": [101, 102]}
    assert check(body) == permits.MALFORMED


def test_trailing_garbage_after_the_arguments_is_refused():
    # The body no longer parses as JSON, so there is no trustworthy envelope: missing.
    text, minted = mint()
    raw = wire(text, minted) + b" garbage"
    assert check(raw) == permits.MISSING
    assert permits.REPLAYED != check(raw)
    assert check(wire(text, minted)) == permits.OK  # and the permit was not burnt


def test_an_envelope_that_is_not_followed_by_a_comma_is_refused():
    text, minted = mint()
    envelope = json.dumps({"secret": SECRET, "permit": minted}, separators=(",", ":"))
    assert check(('{"_mcp":' + envelope + ' "x":1}').encode("ascii")) == permits.MISSING
    # split_wire itself, called directly, also refuses this shape
    assert permits.split_wire(('{"_mcp":' + envelope + ' "x":1}').encode("ascii")) is None


# ---- missing and not configured -------------------------------------------------------

def test_an_envelope_without_a_permit_is_missing():
    raw = permit.wire_text('{"element_ids":[101]}', {"secret": SECRET}).encode("ascii")
    assert check(raw) == permits.MISSING


def test_a_body_without_an_envelope_is_missing():
    assert check(b'{"element_ids":[101]}') == permits.MISSING


@pytest.mark.parametrize("raw", [b"", "", b"null", b"[]", b"not json", b"\xff\xfe\x00", None, 7],
                         ids=["empty_bytes", "empty_text", "null", "list", "garbage", "binary",
                              "none", "int"])
def test_garbage_is_refused_without_raising(raw):
    verdict = check(raw)
    assert verdict in (permits.MISSING, permits.MALFORMED)


def test_empty_bytes_are_missing():
    assert check(b"") == permits.MISSING


@pytest.mark.parametrize("secret,session", [
    (None, SESSION), (SECRET, None), ("", SESSION), (SECRET, ""), ("   ", SESSION),
    (SECRET, "   "), (None, None), (7, SESSION), (SECRET, 7),
], ids=["no_secret", "no_session", "empty_secret", "empty_session", "blank_secret",
        "blank_session", "neither", "int_secret", "int_session"])
def test_without_a_secret_or_a_process_identity_nothing_is_verified(secret, session):
    text, minted = mint()
    assert check(wire(text, minted), secret=secret, session=session) == permits.NOT_CONFIGURED


def test_not_configured_does_not_burn_the_nonce():
    text, minted = mint()
    raw = wire(text, minted)
    assert check(raw, secret=None) == permits.NOT_CONFIGURED
    assert check(raw) == permits.OK


# ---- edge forms of the wire text ------------------------------------------------------

@pytest.mark.parametrize("args", [
    {},
    {"name": "Стена"},
    {"name": "Wall", "nested": {"a": [1, 2, {"b": None}]}},
    {"v": [0.1, 1e16, -2.5]},
    {"v": [1e-7, 123456789012345678, 0.30000000000000004]},
    {"flag": True, "none": None, "text": 'quote " and back\\slash'},
], ids=["empty_object", "cyrillic", "nested", "floats", "float_extremes", "specials"])
def test_edge_forms_of_the_arguments_verify(args):
    text, minted = mint(args=args)
    raw = wire(text, minted)
    assert raw == raw.decode("ascii").encode("ascii")
    assert check(raw) == permits.OK


def test_the_cyrillic_form_travels_escaped_and_is_pure_ascii():
    text = permit.args_text({"name": "Стена"})
    assert text == '{"name":"\\u0421\\u0442\\u0435\\u043d\\u0430"}'
    text, minted = mint(args={"name": "Стена"})
    assert check(wire(text, minted)) == permits.OK


def test_the_empty_object_wire_form_splits_back_to_an_empty_object():
    text, minted = mint(args={})
    assert text == "{}"
    envelope, rest = permits.split_wire(wire(text, minted))
    assert rest == "{}"
    assert envelope["permit"] == minted


def test_split_wire_and_the_trusted_split_agree_on_the_envelope():
    text, minted = mint(args={"a": 1, "b": [0.1]})
    raw = wire(text, minted)
    assert permits.split_wire(raw)[0] == trust.split_envelope(raw)[0]


# ---- no leakage -----------------------------------------------------------------------

def test_verdicts_are_fixed_words_that_carry_neither_body_nor_secret():
    cases = []
    text, minted = mint()
    cases.append(check(wire(text.replace("101", "102"), minted)))
    text, minted = mint()
    minted["m"] = "0" * 64
    cases.append(check(wire(text, minted)))
    cases.append(check(b"nonsense"))
    for verdict in cases:
        assert verdict in ALL_VERDICTS
        assert SECRET not in verdict and "element_ids" not in verdict


# ---- the refusal body -----------------------------------------------------------------

def test_the_failure_status_is_403():
    assert permits.FAILURE_STATUS == 403


@pytest.mark.parametrize("verdict", [v for v in ALL_VERDICTS if v != permits.OK])
def test_every_refusal_has_the_same_closed_body_and_says_nothing_was_changed(verdict):
    body, status = permits.failure(verdict)
    assert status == 403
    assert set(body) == {"error", "permit", "hint"}
    assert body["permit"] == verdict
    assert verdict in body["error"]
    assert body["error"].endswith("Nothing was changed.")
    assert isinstance(body["hint"], str) and body["hint"]
    assert SECRET not in json.dumps(body)


def test_a_missing_permit_hint_names_the_update_in_both_languages():
    body, _ = permits.failure(permits.MISSING)
    hint = body["hint"]
    assert "обновите revitmcp и перезапустите сессию ассистента" in hint.lower()
    assert "Run Update RevitMCP and restart the assistant session" in hint


def test_a_replayed_permit_hint_asks_for_a_new_confirmation_window():
    body, _ = permits.failure(permits.REPLAYED)
    assert "new confirmation window" in body["hint"]
    assert "новое окно подтверждения" in body["hint"]


def test_not_configured_says_to_reinstall_and_restart_revit():
    body, _ = permits.failure(permits.NOT_CONFIGURED)
    assert "Reinstall the extension" in body["hint"]
    assert "fully restart Revit" in body["hint"]


@pytest.mark.parametrize("verdict", ["nonsense", "", None, 7, "OK"])
def test_an_unknown_verdict_is_reported_as_malformed(verdict):
    body, status = permits.failure(verdict)
    assert status == 403
    assert body["permit"] == permits.MALFORMED
    assert body["error"] == "Mutation rejected: one-time permit malformed. Nothing was changed."


def test_the_status_advertisement_names_the_protocol():
    assert permits.status_info() == {"protocol": permits.PERMIT_PROTOCOL}
    assert permits.status_info()["protocol"] == permit.PERMIT_PROTOCOL == 1


def test_both_halves_share_the_mac_vocabulary():
    assert permits.MAC_PREFIX == permit.MAC_PREFIX == "permit1"
    assert permits.KEY_LABEL == permit.KEY_LABEL
    assert permits.PERMIT_KEY == permit.PERMIT_KEY
