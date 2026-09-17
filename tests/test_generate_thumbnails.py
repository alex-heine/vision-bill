import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_thumbnails.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_thumbnails", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_finds_file_under_extra_dir(tmp_path: Path) -> None:
    mod = _load()
    target = tmp_path / "receipt_1.png"
    target.write_bytes(b"x")
    # stored path is container-absolute; the file actually lives under tmp_path
    assert mod._resolve("/app/uploads/receipt_1.png", [str(tmp_path)]) == target


def test_resolve_uses_stored_path_when_it_exists(tmp_path: Path) -> None:
    mod = _load()
    direct = tmp_path / "direct.png"
    direct.write_bytes(b"x")
    assert mod._resolve(str(direct), []) == direct


def test_resolve_returns_none_when_missing(tmp_path: Path) -> None:
    mod = _load()
    assert mod._resolve("/app/uploads/nope.png", [str(tmp_path)]) is None


def test_resolve_empty_returns_none() -> None:
    mod = _load()
    assert mod._resolve("", []) is None
