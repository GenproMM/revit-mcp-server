from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_local_revit_bridge_ignores_environment_proxies():
    """Local pyRevit Routes calls must never use inherited proxy settings."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    client_block = source.split("def _get_client()", 1)[1].split(
        "async def revit_get", 1
    )[0]

    assert "trust_env=False" in client_block