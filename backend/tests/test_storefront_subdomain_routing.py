"""<slug>.order.jdsstudio.ca resolves through the Canner web proxy (beta finding B)."""

from __future__ import annotations

from types import SimpleNamespace

from app.platform.config import storefront_request_host


def _req(headers):
    lowered = {k.lower(): v for k, v in headers.items()}
    return SimpleNamespace(headers=lowered, url=SimpleNamespace(hostname="jds-beta-api.canner.app"))


def test_dedicated_header_used_when_secret_matches(monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", "order.jdsstudio.ca")
    monkeypatch.setenv("JDS_STOREFRONT_PROXY_SECRET", "s3cret-value")
    monkeypatch.delenv("JDS_TRUST_PROXY_STOREFRONT_HOST", raising=False)
    request = _req({"host": "jds-beta-api.canner.app", "x-forwarded-host": "jds-beta-api.canner.app",
                    "x-jds-storefront-host": "maple.order.jdsstudio.ca", "x-jds-proxy-secret": "s3cret-value"})
    assert storefront_request_host(request) == "maple.order.jdsstudio.ca"


def test_dedicated_header_ignored_without_matching_secret(monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", "order.jdsstudio.ca")
    monkeypatch.setenv("JDS_STOREFRONT_PROXY_SECRET", "s3cret-value")
    for supplied in ("wrong", ""):
        request = _req({"host": "jds-beta-api.canner.app", "x-jds-storefront-host": "maple.order.jdsstudio.ca",
                        "x-jds-proxy-secret": supplied})
        assert storefront_request_host(request) == "jds-beta-api.canner.app"
    monkeypatch.delenv("JDS_STOREFRONT_PROXY_SECRET")
    request = _req({"host": "jds-beta-api.canner.app", "x-jds-storefront-host": "maple.order.jdsstudio.ca",
                    "x-jds-proxy-secret": ""})
    assert storefront_request_host(request) == "jds-beta-api.canner.app"


def test_dedicated_header_must_be_one_label_under_base(monkeypatch):
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", "order.jdsstudio.ca")
    monkeypatch.setenv("JDS_STOREFRONT_PROXY_SECRET", "s3cret-value")
    for bad in ("a.b.order.jdsstudio.ca", "evil.example.com", "order.jdsstudio.ca"):
        request = _req({"host": "jds-beta-api.canner.app", "x-jds-storefront-host": bad, "x-jds-proxy-secret": "s3cret-value"})
        assert storefront_request_host(request) == "jds-beta-api.canner.app"
