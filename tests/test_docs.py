"""Keep README / DESIGN / INTENT / AGENTS in sync with the code.

If one of these fails, update the docs (see AGENTS.md "Keeping docs up to date");
don't weaken the test.
"""

import re
from pathlib import Path

import pytest

from miyagi.conditions import ALERT_STYLES, DETECTION_MODES, FOCUS_AREA, default_conditions

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "miyagi"


def doc(name: str) -> str:
    path = ROOT / name
    assert path.is_file(), f"{name} is missing"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["README.md", "DESIGN.md", "INTENT.md", "AGENTS.md", "CLAUDE.md"])
def test_docs_exist(name):
    assert doc(name).strip()


def test_readme_habit_table_matches_conditions():
    readme = doc("README.md")
    rows = [line for line in readme.splitlines() if line.startswith("|")]
    for c in default_conditions().values():
        row = next((r for r in rows if c.label in r), None)
        assert row, f"README habit table is missing '{c.label}' ({c.id})"
        default = [cell.strip().lower() for cell in row.strip("|").split("|")][1]
        expected = "on" if c.enabled else "off"
        assert default.strip("*").startswith(expected), (
            f"README says '{default}' for {c.id}, code default is {expected}"
        )
        if c.focus:
            assert "focus" in default, f"README should mark {c.id} as focus"


def test_design_documents_every_habit_and_constant_sets():
    design = doc("DESIGN.md")
    for cid in default_conditions():
        assert f"`{cid}`" in design, f"DESIGN.md §5 is missing habit `{cid}`"
    for name in ALERT_STYLES + DETECTION_MODES:
        assert f"`{name}`" in design, f"DESIGN.md doesn't mention `{name}`"


def test_intent_reflects_focus_area():
    intent = doc("INTENT.md")
    assert FOCUS_AREA.lower().replace("&", "").split()[0] in intent.lower()
    for c in default_conditions().values():
        if c.focus:
            assert f"`{c.id}`" in intent, f"INTENT.md 'Current focus' should name `{c.id}`"


def _env_vars_in_code() -> set[str]:
    names: set[str] = set()
    for py in PKG.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        names |= set(re.findall(r'os\.environ(?:\.get|\.setdefault)?\(\s*"([A-Z0-9_]+)"', src))
        names |= set(re.findall(r'os\.environ\[\s*"([A-Z0-9_]+)"', src))
        names |= set(re.findall(r'_env_true\(\s*"([A-Z0-9_]+)"', src))
    return names - {"XDG_CACHE_HOME", "XDG_DATA_HOME"}  # standard, mentioned in the defaults column


def test_readme_documents_every_env_var():
    readme = doc("README.md")
    names = _env_vars_in_code()
    assert "MIYAGI_PORT" in names, "env-var scan is broken"
    missing = sorted(n for n in names if f"`{n}`" not in readme and n not in readme)
    assert not missing, f"README.md is missing env vars: {missing}"


def test_design_documents_ws_protocol():
    design = doc("DESIGN.md")
    kinds = set(re.findall(r'kind == "([a-z_]+)"', (PKG / "server.py").read_text(encoding="utf-8")))
    assert kinds, "protocol scan is broken"
    missing = sorted(k for k in kinds if f"`{k}`" not in design)
    assert not missing, f"DESIGN.md §8 is missing WS message types: {missing}"


def test_design_module_map_is_complete():
    design = doc("DESIGN.md")
    modules = [p.name for p in PKG.glob("*.py") if p.name != "__init__.py"]
    modules += [f"static/{p.name}" for p in (PKG / "static").glob("*.js")]
    modules += [f"static/{p.name}" for p in (PKG / "static").glob("*.html")]
    missing = sorted(m for m in modules if f"`{m}`" not in design)
    assert not missing, f"DESIGN.md §2 module map is missing: {missing}"


def test_frontend_knows_every_habit():
    app_js = (PKG / "static" / "app.js").read_text(encoding="utf-8")
    avatar_js = (PKG / "static" / "avatar.js").read_text(encoding="utf-8")
    for cid in default_conditions():
        assert f'"{cid}"' in app_js, f"app.js PRIORITY is missing {cid}"
        assert re.search(rf"\b{cid}\s*:", avatar_js), f"avatar.js MOODS is missing {cid}"


def test_agents_md_has_doc_maintenance_rules():
    agents = doc("AGENTS.md")
    assert "Keeping docs up to date" in agents
    for name in ("README.md", "DESIGN.md", "INTENT.md", "test_docs.py"):
        assert name in agents
    assert "@AGENTS.md" in doc("CLAUDE.md")


STATIC = PKG / "static"


def _icons_used() -> set[str]:
    used: set[str] = set()
    for f in [STATIC / "index.html", STATIC / "app.js"]:
        src = f.read_text(encoding="utf-8")
        used |= set(re.findall(r'class="icon[^"]*">([a-z0-9_]+)<', src))
    used |= set(re.findall(r'banner = \["([a-z0-9_]+)"', (STATIC / "app.js").read_text(encoding="utf-8")))
    used |= set(re.findall(r'notice\("([a-z0-9_]+)"', (STATIC / "app.js").read_text(encoding="utf-8")))
    return used


def test_every_ui_icon_is_in_the_bundled_subset():
    listed = {
        ln.strip()
        for ln in (STATIC / "fonts" / "icons.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    used = _icons_used()
    assert {"videocam", "check"} <= used, "icon scan is broken"
    missing = sorted(used - listed)
    assert not missing, f"Add to static/fonts/icons.txt and run scripts/fetch_fonts.py: {missing}"


def test_brand_assets_present():
    for name in ("miyagi-192.png", "miyagi-64.png", "favicon-32.png"):
        assert (STATIC / "brand" / name).stat().st_size > 1_000, f"missing brand asset {name}"
    for page in ("index.html", "coach.html"):
        assert "/static/brand/favicon-32.png" in (STATIC / page).read_text(encoding="utf-8")


def test_bundled_fonts_present():
    for name in ("google-sans-flex-latin.woff2", "roboto-mono-latin.woff2", "material-symbols-rounded.woff2"):
        assert (STATIC / "fonts" / name).stat().st_size > 10_000, f"missing font {name}"


def test_ui_makes_no_third_party_requests():
    for f in [
        STATIC / "index.html",
        STATIC / "coach.html",
        STATIC / "app.js",
        STATIC / "avatar.js",
        STATIC / "style.css",
    ]:
        assert not re.search(r"https?://", f.read_text(encoding="utf-8")), f"{f.name} references an external URL"


def test_css_uses_m3_tokens():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for role in ("primary", "on-primary", "surface", "on-surface", "secondary-container", "outline", "error"):
        assert f"--md-sys-color-{role}:" in css
    assert "prefers-color-scheme: dark" in css and "Google Sans Flex" in css
