import pytest

from asset_compass.taxonomy import normalize_tag, parse_formats, parse_tags
from asset_compass.urls import canonicalize_url


def test_canonical_url_drops_tracking_but_preserves_resource_identity():
    assert canonicalize_url(" HTTPS://Example.COM:443/asset?id=12&utm_source=mail#section ") == "https://example.com/asset?id=12"
    assert canonicalize_url("http://example.com:80") == "http://example.com/"
    assert canonicalize_url("https://example.com/asset?id=13") != canonicalize_url("https://example.com/asset?id=12")


@pytest.mark.parametrize("bad", ["file:///tmp/asset", "javascript:alert(1)", "example.com", "https://a:b@example.org/path", "https://example.com:bad"])
def test_bad_urls_rejected(bad):
    with pytest.raises(ValueError):
        canonicalize_url(bad)


def test_normalization_and_deduplication():
    assert normalize_tag("Low Poly") == "low-poly"
    assert parse_tags(" 3D, low poly, low-poly, pixel art ") == ["3d", "low-poly", "pixel-art"]
    assert parse_formats(".GLTF, fbx, FBX") == ["fbx", "gltf"]
    with pytest.raises(ValueError):
        normalize_tag("---")

