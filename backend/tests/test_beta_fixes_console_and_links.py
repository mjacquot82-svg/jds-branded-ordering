"""Beta QA fixes: optional storefront bootstrap on operations pages and beta shop links."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import catalog
from app.tenancy.pilot_shop import pilot_shop_link_base, pilot_shop_url


def _request(query: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/storefront/bootstrap", "query_string": query.encode(), "headers": []})


def _missing(*_args, **_kwargs):
    raise HTTPException(404, detail={"code": "tenant_not_found"})


def test_optional_bootstrap_returns_none_only_when_asked(monkeypatch):
    monkeypatch.setattr(catalog, "ladels_compatibility_tenant", _missing)
    assert catalog.optional_storefront_tenant(_request("optional=1"), None) is None
    with pytest.raises(HTTPException) as raised:
        catalog.optional_storefront_tenant(_request(""), None)
    assert raised.value.status_code == 404


def test_optional_bootstrap_does_not_hide_other_errors(monkeypatch):
    def boom(*_a, **_k):
        raise HTTPException(500)
    monkeypatch.setattr(catalog, "ladels_compatibility_tenant", boom)
    with pytest.raises(HTTPException):
        catalog.optional_storefront_tenant(_request("optional=1"), None)


def test_bootstrap_endpoint_answers_204_for_optional_miss():
    from app.api.v1.platform import storefront_bootstrap
    from fastapi import Response
    result = storefront_bootstrap(_request("optional=1"), Response(), None, None)
    assert result.status_code == 204


def test_shop_link_base_follows_env(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://jds-beta-web.canner.app/")
    monkeypatch.setenv("JDS_ENVIRONMENT", "beta")
    monkeypatch.setenv("JDS_PILOT_SHOP_LINKS", "true")
    assert pilot_shop_link_base() == "https://jds-beta-web.canner.app/?shop="
    assert pilot_shop_url("zz-test") == "https://jds-beta-web.canner.app/?shop=zz-test"
    monkeypatch.setenv("JDS_ENVIRONMENT", "production")
    assert pilot_shop_link_base() is None
    monkeypatch.setenv("JDS_ENVIRONMENT", "beta")
    monkeypatch.setenv("JDS_PILOT_SHOP_LINKS", "false")
    assert pilot_shop_link_base() is None


def _host_request(host: str, forwarded: str = "") -> Request:
    headers = [(b"host", host.encode())] + ([(b"x-forwarded-host", forwarded.encode())] if forwarded else [])
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": headers, "server": (host, 443), "scheme": "https"})


def test_proxied_shop_subdomain_is_used_only_when_trusted_and_one_label(monkeypatch):
    from app.platform.config import storefront_request_host
    monkeypatch.setenv("JDS_STOREFRONT_BASE_DOMAIN", "order.jdsstudio.ca")
    req = _host_request("jds-beta-api.canner.app", "maple.order.jdsstudio.ca")
    monkeypatch.delenv("JDS_TRUST_PROXY_STOREFRONT_HOST", raising=False)
    assert storefront_request_host(req) == "jds-beta-api.canner.app"
    monkeypatch.setenv("JDS_TRUST_PROXY_STOREFRONT_HOST", "true")
    assert storefront_request_host(req) == "maple.order.jdsstudio.ca"
    assert storefront_request_host(_host_request("api", "a.b.order.jdsstudio.ca")) == "api"
    assert storefront_request_host(_host_request("api", "evil.example.com")) == "api"
    assert storefront_request_host(_host_request("api", "order.jdsstudio.ca")) == "api"
