"""Public SEO tool landing pages."""

from __future__ import annotations

from app.seo_tools import LANDINGS, get_landing, list_landings


def test_landing_catalogue_complete():
    assert len(list_landings()) >= 5
    for slug in (
        "psychrometric-calculator",
        "mixed-air-calculator",
        "duct-sizing-calculator",
        "chilled-water-pipe-sizing",
        "lthw-pipe-pressure-drop",
    ):
        assert get_landing(slug) is not None
        assert slug in LANDINGS


def test_every_landing_has_explicit_access():
    for landing in list_landings():
        assert landing.access in ("free", "pro"), landing.slug
        if landing.free_view:
            assert landing.access == "free", landing.slug
        if landing.access == "pro":
            assert not landing.free_view, landing.slug


def test_tools_index_and_landing_are_public(app):
    client = app.test_client()
    r = client.get("/tools/")
    assert r.status_code == 200
    assert b"HVAC calculator guides" in r.data
    assert b"psychrometric-calculator" in r.data
    body = r.get_data(as_text=True)
    assert 'class="access-badge access-badge--free"' in body
    assert 'class="access-badge access-badge--pro"' in body
    assert ">FREE</span>" in body
    assert ">PRO</span>" in body
    assert "tool-access-free" in body
    # Free calculators appear before Pro landings in the catalogue.
    assert body.find("access-badge--free") < body.find("access-badge--pro")

    r2 = client.get("/tools/mixed-air-calculator")
    assert r2.status_code == 200
    assert b"mixed air" in r2.data.lower()
    assert b"How to use" in r2.data


def test_unknown_tool_landing_404(app):
    assert app.test_client().get("/tools/not-a-real-tool").status_code == 404


def test_sitemap_includes_tool_landings(app):
    r = app.test_client().get("/sitemap.xml")
    assert r.status_code == 200
    body = r.data.decode()
    assert "/tools/" in body
    assert "/tools/psychrometric-calculator" in body
    assert "/tools/chilled-water-pipe-sizing" in body
    assert "/methodology" in body
    assert "/reference/cooling-coil-design" in body
    assert "/reference/pipe-sizing-design-limits" in body
    assert "<lastmod>" in body
    assert "/v2/" not in body
