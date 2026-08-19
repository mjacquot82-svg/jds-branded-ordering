import base64
import os
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import ValidationError
from requests.exceptions import ConnectionError, Timeout
from app.api.v1.customer_push import SubscriptionInput
from app.communications.service import lunch_special_message
from app.push.config import PushSettings
from app.push.dispatcher import PushDispatcher
from app.push.models import PushAnnouncement
from app.push.provider import PyWebPushProvider, classify_exception, classify_status
from app.push.security import SubscriptionProtector, endpoint_fingerprint

def test_push_release_requires_complete_valid_configuration():
    assert PushSettings(release_enabled=True).active is False
    key=Fernet.generate_key().decode()
    public="B"+"A"*86
    settings=PushSettings(vapid_private_key="private",vapid_public_key=public,vapid_subject="mailto:test@example.com",encryption_key=key,release_enabled=True)
    assert settings.active is True
    assert settings.can_enroll is True

def test_enrollment_can_be_enabled_without_enabling_sends():
    key=Fernet.generate_key().decode(); public="B"+"A"*86
    settings=PushSettings(vapid_private_key="private",vapid_public_key=public,vapid_subject="mailto:test@example.com",encryption_key=key,enrollment_enabled=True)
    assert settings.can_enroll is True
    assert settings.active is False

def test_subscription_request_schema_accepts_allowlisted_payload_and_remains_strict():
    payload={"endpoint":"https://push.example.test/device","keys":{"p256dh":"B"+"A"*86,"auth":"A"*22},"content_encoding":"aes128gcm","device_label":"Android"}
    assert SubscriptionInput.model_validate(payload).endpoint==payload["endpoint"]
    try:
        SubscriptionInput.model_validate({**payload,"expirationTime":None})
    except ValidationError as error:
        assert error.errors()[0]["type"]=="extra_forbidden"
    else:
        raise AssertionError("browser-only fields must remain forbidden")

def test_subscription_capabilities_are_encrypted_and_fingerprinted():
    crypt=SubscriptionProtector(Fernet.generate_key().decode()); endpoint="https://push.example.test/private-capability"
    protected=crypt.encrypt(endpoint)
    assert endpoint.encode() not in protected
    assert crypt.decrypt(protected)==endpoint
    assert endpoint_fingerprint(endpoint)==endpoint_fingerprint(endpoint)

def test_backend_owns_standard_lunch_special_format():
    assert lunch_special_message("Soup & Sandwich",1295)=="Today’s Lunch Special is Soup & Sandwich for $12.95. Order online while it’s available!"

def test_provider_classifies_acceptance_expiry_retry_and_permanent_errors():
    assert classify_status(201).accepted is True
    assert classify_status(202).accepted is True
    assert classify_status(410).expired is True
    assert classify_status(429).permanent is False
    assert classify_status(503).permanent is False
    assert classify_status(None).permanent is False
    assert classify_status(400).permanent is True

def test_provider_applies_bounded_transport_settings_without_leaking_errors():
    captured={}
    class Response: status_code=202
    def send_impl(**kwargs): captured.update(kwargs); return Response()
    settings=PushSettings(vapid_private_key="secret",vapid_subject="mailto:test@example.com",request_timeout_seconds=7)
    result=PyWebPushProvider(settings,send_impl).send({"endpoint":"https://push.invalid/capability","keys":{}},{"version":1},600,"normal","topic")
    assert result.accepted is True
    assert captured["timeout"]==7
    assert captured["ttl"]==600
    assert captured["headers"]=={"Urgency":"normal","Topic":"topic"}

def test_provider_converts_pem_vapid_key_before_pywebpush_invocation():
    private_key=ec.generate_private_key(ec.SECP256R1())
    pem=private_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    captured={}
    class Response: status_code=202
    def send_impl(**kwargs): captured.update(kwargs); return Response()
    settings=PushSettings(vapid_private_key=pem,vapid_subject="mailto:test@example.com")
    result=PyWebPushProvider(settings,send_impl).send({"endpoint":"https://push.invalid/synthetic","keys":{}},{"version":1},600,"normal","topic")
    assert result.accepted is True
    assert captured["vapid_private_key"].private_key is not None

def test_pem_vapid_signing_and_synthetic_subscription_encryption_prepare_offline():
    from py_vapid import Vapid
    from pywebpush import WebPusher

    private_key=ec.generate_private_key(ec.SECP256R1())
    pem=private_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    vapid=Vapid.from_pem(pem)
    signed=vapid.sign({"sub":"mailto:test@example.com","aud":"https://push.invalid","exp":int((datetime.now(timezone.utc)+timedelta(hours=1)).timestamp())})
    receiver=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    encode=lambda value:base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    subscription={"endpoint":"https://push.invalid/synthetic","keys":{"p256dh":encode(receiver),"auth":encode(os.urandom(16))}}
    prepared=WebPusher(subscription)._prepare_send_data(b'{"synthetic":true}',{"Urgency":"normal","Topic":"synthetic"},ttl=600,content_encoding="aes128gcm")
    assert set(signed)=={"Authorization"}
    assert prepared["endpoint"]==subscription["endpoint"]
    assert prepared["headers"]["content-encoding"]=="aes128gcm"
    assert prepared["headers"]["ttl"]=="600"
    assert prepared["data"]

def test_provider_sanitizes_pre_http_exception_categories():
    assert classify_exception(Timeout("secret capability")).error_code=="timeout"
    assert classify_exception(ConnectionError("secret capability")).error_code=="connection_error"
    assert classify_exception(RuntimeError("secret capability")).error_code=="provider_error"

def test_provider_sanitizes_pem_parse_failure_as_vapid_error():
    settings=PushSettings(vapid_private_key="-----BEGIN PRIVATE KEY-----\ninvalid\n-----END PRIVATE KEY-----",vapid_subject="mailto:test@example.com")
    result=PyWebPushProvider(settings,lambda **_:None).send({"endpoint":"https://push.invalid/synthetic","keys":{}},{"version":1},600,"normal","topic")
    assert result.error_code=="vapid_error"
    assert result.http_status is None

def test_previous_cafe_day_lunch_special_is_stale():
    announcement=PushAnnouncement(kind="lunch_special",cafe_day=None)
    assert PushDispatcher._lunch_special_is_stale(announcement) is True

def test_general_announcement_has_bounded_staleness():
    expired=PushAnnouncement(kind="general",expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    current=PushAnnouncement(kind="general",expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    legacy=PushAnnouncement(kind="general",expires_at=None)
    assert PushDispatcher._announcement_is_stale(expired) is True
    assert PushDispatcher._announcement_is_stale(current) is False
    assert PushDispatcher._announcement_is_stale(legacy) is True
