# -*- coding: utf-8 -*-
"""Phase 2 preflight (G1-G5): operator procedure and offline evidence classifier.

RED skeleton: nothing is implemented yet.
"""
import sys

UNIMPLEMENTED = "unimplemented"

G1_SNIPPET = ""
G2_SNIPPET = ""
G3_SNIPPET = ""
G4_SNIPPET = ""


def _todo(_record):
    return UNIMPLEMENTED, ["not implemented"]


classify_g1 = classify_g2 = classify_g3 = classify_g4 = classify_g5 = _todo


def classify_all(evidence):
    return {"gates": {}, "overall": UNIMPLEMENTED, "approval": UNIMPLEMENTED}


def evidence_template():
    return {}


def parse_listener_rows(text, ports):
    return {}


def main(argv=None):
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
