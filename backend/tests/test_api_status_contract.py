from pathlib import Path


API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"


def test_api_uses_starlette_compatible_422_status_constant():
    sources = "".join(path.read_text(encoding="utf-8") for path in API_DIR.glob("*.py"))

    assert "HTTP_422_UNPROCESSABLE_CONTENT" not in sources
    assert "HTTP_422_UNPROCESSABLE_ENTITY" not in sources
    assert "status_code=422" in sources
