from datetime import datetime, timezone
from html import escape
import hashlib
import os
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.catalog import get_catalog_session, ladels_compatibility_tenant
from app.api.v1.owner_auth import csrf_principal, current_principal
from app.api.v1.tenant_context import authenticated_owner_tenant
from app.jds_auth.models import JdsApplication, JdsUser, Membership, MerchantAcquisition, Organization, Role
from app.jds_auth.config import AuthSettings
from app.clover.models import CloverInstallation
from app.catalog.models import Product
from app.jds_auth.service import AuthPrincipal
from app.platform.assets import launch_qr_svg, tenant_icon_png, tenant_media_icon_png
from app.platform.acquisition import AcquisitionError, AcquisitionRequest, MerchantAcquisitionService
from app.platform.config import STANDARD_STOREFRONT_BASE_DOMAIN, hosted_storefront_hostname, storefront_base_domain, storefront_url
from app.platform.design import DEFAULT_CONFIG, DesignService, DesignValidationError
from app.platform.entitlements import entitlement_features
from app.platform.models import BillingPlan, BusinessProfile, DesignMediaReference, DesignVersion, DesignWorkspace, MediaAsset, OnboardingState, OperationalAuditEvent, OrganizationSubscription, PlatformGrant, StorefrontHostname
from app.platform.media import MediaStorage, MediaStorageError, MediaValidationError, default_media_storage, image_dimensions, prepare_image
from app.platform.starter_media import STARTER_MEDIA_ASSETS, starter_asset_available, starter_asset_path, starter_reference
from app.platform.readiness import evaluate_publish_readiness, evaluate_storefront_readiness, onboarding_completed_steps, synchronize_public_readiness
from app.tenancy.context import TenantContext

router = APIRouter(tags=["platform"])
class Strict(BaseModel): model_config = ConfigDict(extra="forbid")
class DraftInput(Strict): revision: int = Field(ge=1); config: dict
class RevertInput(Strict): version_id: UUID
class OnboardingInput(Strict): revision: int = Field(ge=1); current_step: str = Field(max_length=50); completed_steps: list[str] = Field(max_length=20)
class MediaInput(Strict):
    storage_key: str = Field(min_length=1, max_length=500, pattern=r"^[a-zA-Z0-9/_-]+\.[a-zA-Z0-9]+$")
    media_type: str = Field(pattern=r"^image/(png|jpeg|webp)$")
    alt_text: str = Field(default="", max_length=300)
    byte_size: int = Field(gt=0, le=10_000_000)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
class BusinessAddressInput(Strict):
    street: str = Field(default="", max_length=240)
    city: str = Field(default="", max_length=120)
    region: str = Field(default="", max_length=120)
    postal_code: str = Field(default="", max_length=30)
    country: str = Field(default="CA", max_length=80)
class BusinessSocialsInput(Strict):
    instagram: str = Field(default="", max_length=500)
    facebook: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=500)
class BusinessInput(Strict):
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=240)
    contact_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    address: BusinessAddressInput = Field(default_factory=BusinessAddressInput)
    socials: BusinessSocialsInput = Field(default_factory=BusinessSocialsInput)
    timezone: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="CAD", pattern=r"^[A-Z]{3}$")
    pickup_instructions: str = Field(default="", max_length=1000)
    fulfillment_wording: str = Field(default="Pickup", min_length=1, max_length=120)
class ProvisionOrganizationInput(Strict):
    slug: str = Field(min_length=3,max_length=63,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=1,max_length=200)
    owner_email: str = Field(min_length=3,max_length=320)
    acquisition_source: str = Field(default="platform", pattern=r"^(clover|direct|invitation|platform)$")
    requested_plan_key: str | None = Field(default=None, max_length=50)
    external_installation_reference: str | None = Field(default=None, max_length=240)
    verified_merchant_reference: str | None = Field(default=None, max_length=240)
    provider_metadata: dict = Field(default_factory=dict)
class StorefrontSlugInput(Strict):
    slug: str = Field(min_length=3,max_length=63,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def design_payload(workspace: DesignWorkspace) -> dict:
    return {"revision": workspace.revision, "config": workspace.draft_config, "published_version_id": str(workspace.published_version_id) if workspace.published_version_id else None}

def media_storage(request: Request) -> MediaStorage:
    return getattr(request.app.state, "media_storage", None) or default_media_storage()

@router.get("/storefront/bootstrap")
def storefront_bootstrap(request: Request, response: Response, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    workspace = session.get(DesignWorkspace, tenant.organization_id)
    version = session.get(DesignVersion, workspace.published_version_id) if workspace and workspace.published_version_id else None
    profile = session.get(BusinessProfile, tenant.organization_id)
    host = session.scalar(select(StorefrontHostname).where(StorefrontHostname.organization_id == tenant.organization_id, StorefrontHostname.is_canonical.is_(True), StorefrontHostname.status == "verified"))
    response.headers["Cache-Control"] = f"public, max-age=60" if version else "no-store"
    response.headers["Vary"] = "Host"
    staging = bool(getattr(request.app.state, "staging_review_enabled", False))
    return {"tenant": {"id": str(tenant.organization_id), "slug": tenant.organization_slug, "canonicalHost": host.hostname if host else None}, "business": {"displayName": profile.display_name if profile else tenant.organization_slug, "timezone": profile.timezone if profile else "America/Toronto", "currency": profile.currency if profile else "CAD", "pickupInstructions": profile.pickup_instructions if profile else ""}, "design": version.config if version else DEFAULT_CONFIG, "designVersion": version.version_number if version else 0, "review": {"staging": staging, "label": "STAGING — NO REAL TRANSACTIONS" if staging else None, "paymentMode": getattr(request.app.state, "payment_mode", "production") if staging else "production"}}

@router.get("/storefront/manifest.webmanifest")
def manifest(response: Response, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    workspace = session.get(DesignWorkspace, tenant.organization_id); version = session.get(DesignVersion, workspace.published_version_id) if workspace and workspace.published_version_id else None
    config = version.config if version else DEFAULT_CONFIG; pwa = config.get("pwa", {})
    version_key=version.version_number if version else 0; cache_key=f"tenant={tenant.organization_id}&v={version_key}"
    response.headers["Cache-Control"]="public, max-age=60" if version else "no-store";response.headers["Vary"]="Host"
    return {"id": f"/{tenant.organization_slug}", "name": config.get("displayName", "Order ahead"), "short_name": pwa.get("shortName", "Order"), "start_url": "/", "scope": "/", "display": "standalone", "theme_color": pwa.get("themeColor", "#6f7d5f"), "background_color": pwa.get("backgroundColor", "#f7f0e6"), "icons":[{"src":f"/api/v1/storefront/icon/192.png?{cache_key}","sizes":"192x192","type":"image/png","purpose":"any"},{"src":f"/api/v1/storefront/icon/512.png?{cache_key}","sizes":"512x512","type":"image/png","purpose":"any"},{"src":f"/api/v1/storefront/icon/192.png?maskable=1&{cache_key}","sizes":"192x192","type":"image/png","purpose":"maskable"},{"src":f"/api/v1/storefront/icon/512.png?maskable=1&{cache_key}","sizes":"512x512","type":"image/png","purpose":"maskable"}]}

@router.get("/storefront/icon/{size}.png")
def storefront_icon(size: int, request: Request, maskable: bool = False, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    workspace=session.get(DesignWorkspace,tenant.organization_id);version=session.get(DesignVersion,workspace.published_version_id) if workspace and workspace.published_version_id else None
    config=version.config if version else DEFAULT_CONFIG;colors=config.get("colors",{});icon_id=config.get("appIconMediaId")
    try:
        item=session.scalar(select(MediaAsset).where(MediaAsset.id==UUID(str(icon_id)),MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active")) if icon_id else None
        if item:
            content=tenant_media_icon_png(media_storage(request).read(item.storage_key),size,colors.get("primary","#6f7d5f"),position,contain=str(icon_id)==str(config.get("logoMediaId")),maskable=maskable)
        else: content=tenant_icon_png(size,colors.get("primary","#6f7d5f"),colors.get("accent","#b98564"),maskable=maskable)
    except ValueError as error: raise HTTPException(404,detail="Icon not found.") from error
    return Response(content=content,media_type="image/png",headers={"Cache-Control":"public, max-age=31536000, immutable","Vary":"Host"})

@router.get("/owner/design")
def get_design(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"; return design_payload(DesignService(session, tenant).workspace())

@router.get("/owner/design/versions")
def design_versions(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    workspace = DesignService(session, tenant).workspace()
    rows = session.scalars(select(DesignVersion).where(DesignVersion.organization_id == tenant.organization_id).order_by(DesignVersion.version_number.desc())).all()
    return [{"id":str(item.id),"version":item.version_number,"publishedAt":item.created_at,"isCurrent":item.id == workspace.published_version_id,"sourceVersionId":str(item.source_version_id) if item.source_version_id else None} for item in rows]

@router.put("/owner/design")
def save_design(payload: DraftInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try: return design_payload(DesignService(session, tenant).save(payload.config, payload.revision, principal.user_id))
    except DesignValidationError as error: raise HTTPException(409, detail={"code":"design_invalid","message":str(error)}) from error

@router.post("/owner/design/publish")
def publish_design(principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    readiness = evaluate_publish_readiness(session, tenant.organization_id)
    if not readiness.public_ready:
        raise HTTPException(409, detail={"code":"storefront_not_ready","message":"Complete required commerce setup before publishing.","checks":readiness.checks})
    try:
        item = DesignService(session, tenant).publish(principal.user_id)
        synchronize_public_readiness(session,tenant.organization_id);session.commit()
        return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(422, detail={"code":"design_invalid","message":str(error)}) from error

@router.post("/owner/design/revert")
def revert_design(payload: RevertInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    try:
        item = DesignService(session, tenant).revert(payload.version_id, principal.user_id); return {"id":str(item.id),"version":item.version_number}
    except DesignValidationError as error: raise HTTPException(404, detail={"code":"version_not_found","message":str(error)}) from error

@router.get("/owner/design/preview")
def design_preview(response: Response, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    response.headers["Cache-Control"]="private, no-store"
    workspace=DesignService(session,tenant).workspace();profile=session.get(BusinessProfile,tenant.organization_id)
    assets=session.scalars(select(MediaAsset).where(MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active")).all()
    return {"tenant":{"id":str(tenant.organization_id),"slug":tenant.organization_slug},"business":business_payload(profile) if profile else None,"design":workspace.draft_config,"draftRevision":workspace.revision,"checkoutEnabled":False,"media":[{"id":str(asset.id),"url":f"/api/v1/owner/media/{asset.id}/content","altText":asset.alt_text} for asset in assets]}

@router.get("/owner/businesses")
def businesses(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows = session.execute(select(Membership, Organization, Role).join(Organization, Organization.id == Membership.organization_id).join(Role, Role.id == Membership.role_id).where(Membership.user_id == principal.user_id, Membership.status == "active", Organization.is_active.is_(True)).order_by(Organization.name)).all()
    return [{"membershipId":str(m.id),"organizationId":str(o.id),"slug":o.slug,"name":o.name,"role":r.key,"selected":o.id == principal.organization_id} for m,o,r in rows]

@router.get("/owner/onboarding")
def onboarding(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.get(OnboardingState, tenant.organization_id) or OnboardingState(organization_id=tenant.organization_id)
    if item not in session: session.add(item); session.commit()
    return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision,"initialSetupCompletedAt":item.initial_setup_completed_at,"initialLaunchSource":item.initial_launch_source}

@router.get("/owner/readiness")
def readiness(request: Request, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    result = evaluate_storefront_readiness(session, tenant.organization_id)
    review_mode = "staging" if getattr(request.app.state,"staging_review_enabled",False) else "local" if getattr(request.app.state,"local_review_enabled",False) else None
    return {"publicReady": result.public_ready, "checks": result.checks, "reviewMode":review_mode}

@router.post("/owner/readiness/recheck")
def recheck_readiness(principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    result=synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.readiness_checked",target_type="organization",target_id=str(tenant.organization_id),outcome="ready" if result.public_ready else "incomplete",metadata_json={"checks":result.checks}));session.commit()
    return {"publicReady":result.public_ready,"checks":result.checks}

@router.get("/owner/storefront")
def owner_storefront(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    rows=session.scalars(select(StorefrontHostname).where(StorefrontHostname.organization_id==tenant.organization_id).order_by(StorefrontHostname.created_at.desc())).all()
    acquisition=session.scalar(select(MerchantAcquisition).where(MerchantAcquisition.organization_id==tenant.organization_id))
    fixture_suggestion=bool(acquisition and acquisition.source in {"local_review","staging_review"} and tenant.organization_slug=="new-merchant-demo")
    slug_is_suggestion=not rows or fixture_suggestion
    configured=hosted_storefront_hostname(tenant.organization_slug)
    current_hostname=next((row.hostname for row in rows if row.is_canonical),None) or (rows[0].hostname if rows else None)
    suffix=current_hostname[len(tenant.organization_slug):] if current_hostname and current_hostname.startswith(tenant.organization_slug) else ""
    return {"slug":tenant.organization_slug,"slugIsSuggestion":slug_is_suggestion,"merchantAddressSuffix":f".{STANDARD_STOREFRONT_BASE_DOMAIN}","addressSuffix":suffix,"configuredHostname":configured,"hostnames":[{"id":str(row.id),"hostname":row.hostname,"status":row.status,"canonical":row.is_canonical} for row in rows]}

@router.get("/owner/storefront/launch-kit")
def launch_kit(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    if not hostname: raise HTTPException(409,detail="Verify a canonical storefront before generating launch assets.")
    url=(f"{os.environ['FRONTEND_URL'].rstrip('/')}?review_tenant={tenant.organization_slug}" if os.getenv("JDS_ENVIRONMENT","").lower()=="staging" and os.getenv("JDS_ENABLE_STAGING_REVIEW","false").lower()=="true" else storefront_url(hostname))
    return {"url":url,"qrUrl":"/api/v1/owner/storefront/launch-kit/qr.svg","printUrl":"/api/v1/owner/storefront/launch-kit/print"}

@router.get("/owner/storefront/launch-kit/qr.svg")
def launch_qr(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    if not hostname: raise HTTPException(409,detail="Verify a canonical storefront first.")
    url=(f"{os.environ['FRONTEND_URL'].rstrip('/')}?review_tenant={tenant.organization_slug}" if os.getenv("JDS_ENVIRONMENT","").lower()=="staging" and os.getenv("JDS_ENABLE_STAGING_REVIEW","false").lower()=="true" else storefront_url(hostname))
    return Response(content=launch_qr_svg(url),media_type="image/svg+xml",headers={"Cache-Control":"private, no-store"})

@router.get("/owner/storefront/launch-kit/print", response_class=HTMLResponse)
def launch_print(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> HTMLResponse:
    hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.status=="verified",StorefrontHostname.is_canonical.is_(True)))
    profile=session.get(BusinessProfile,tenant.organization_id)
    if not hostname or profile is None: raise HTTPException(409,detail="Complete storefront launch setup first.")
    staging=os.getenv("JDS_ENVIRONMENT","").lower()=="staging" and os.getenv("JDS_ENABLE_STAGING_REVIEW","false").lower()=="true"
    staging_url=f"{os.environ['FRONTEND_URL'].rstrip('/')}?review_tenant={tenant.organization_slug}" if staging else ""
    name=escape(profile.display_name);url=escape(staging_url if staging else storefront_url(hostname))
    body=f"""<!doctype html><html><head><title>{name} launch sign</title><style>body{{font-family:system-ui;text-align:center;padding:8vh;color:#222}}h1{{font-size:3rem}}img{{width:min(60vw,420px)}}p{{font-size:1.4rem}}@media print{{button{{display:none}}}}</style></head><body><h1>Order ahead from {name}</h1><img src='/api/v1/owner/storefront/launch-kit/qr.svg' alt='QR code for {name}'><p>{url}</p><button onclick='print()'>Print sign</button></body></html>"""
    return HTMLResponse(body,headers={"Cache-Control":"private, no-store"})

@router.put("/owner/storefront")
def choose_storefront(payload: StorefrontSlugInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    hostname=hosted_storefront_hostname(payload.slug)
    if not hostname: raise HTTPException(503,detail="Hosted storefront domains are not configured in this environment.")
    conflict=session.scalar(select(Organization.id).where(Organization.slug==payload.slug,Organization.id!=tenant.organization_id))
    if conflict or session.scalar(select(StorefrontHostname.id).where(StorefrontHostname.hostname==hostname,StorefrontHostname.organization_id!=tenant.organization_id)):
        raise HTTPException(409,detail="That storefront name is unavailable.")
    organization=session.get(Organization,tenant.organization_id);organization.slug=payload.slug
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.hostname==hostname))
    if item is None:
        item=StorefrontHostname(organization_id=tenant.organization_id,hostname=hostname,status="pending",is_canonical=False);session.add(item)
    # JDS-hosted subdomains under JDS_STOREFRONT_BASE_DOMAIN are platform-owned DNS/TLS.
    # Auto-verify them so merchants are not blocked waiting for a platform admin call.
    # Custom domains (future) still require explicit platform verification.
    base = storefront_base_domain()
    hosted = bool(base) and hostname == f"{payload.slug}.{base}"
    if hosted:
        session.execute(StorefrontHostname.__table__.update().where(StorefrontHostname.organization_id==tenant.organization_id,StorefrontHostname.id!=item.id).values(is_canonical=False))
        item.status="verified";item.is_canonical=True;item.verified_at=datetime.now(timezone.utc)
        action="storefront.hostname_auto_verified"
    else:
        if item.status != "verified":
            item.status="pending";item.is_canonical=False;item.verified_at=None
        action="storefront.hostname_requested"
    synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action=action,target_type="storefront_hostname",target_id=str(item.id),outcome="success",metadata_json={"hostname":hostname,"hosted":hosted}));session.commit()
    return {"id":str(item.id),"slug":payload.slug,"hostname":hostname,"status":item.status,"canonical":bool(item.is_canonical)}

@router.post("/owner/storefront/{hostname_id}/retry")
def retry_storefront(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.id==hostname_id,StorefrontHostname.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Hostname not found.")
    item.status="pending";item.is_canonical=False;item.verified_at=None
    synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.hostname_retried",target_type="storefront_hostname",target_id=str(item.id),outcome="success"));session.commit()
    return {"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":False}

@router.delete("/owner/storefront/{hostname_id}", status_code=204)
def disable_storefront(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    item=session.scalar(select(StorefrontHostname).where(StorefrontHostname.id==hostname_id,StorefrontHostname.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Hostname not found.")
    item.status="disabled";item.is_canonical=False;item.verified_at=None
    synchronize_public_readiness(session,tenant.organization_id)
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="storefront.hostname_disabled",target_type="storefront_hostname",target_id=str(item.id),outcome="success"));session.commit()
    return Response(status_code=204)

def _fixture_customer_value(value: str | None) -> bool:
    normalized=(value or "").strip().lower()
    return ".invalid" in normalized or "@local.jds.test" in normalized or ".local.test" in normalized or normalized in {"https://instagram.com/yourbusiness","https://facebook.com/yourbusiness"}


def _setup_customer_name(session: Session, organization_id: UUID, profile: BusinessProfile) -> str:
    onboarding=session.get(OnboardingState,organization_id)
    workspace=session.get(DesignWorkspace,organization_id)
    design_name=str((workspace.draft_config if workspace else {}).get("displayName","")).strip()
    if onboarding and onboarding.initial_setup_completed_at is None and design_name not in {"","Your business","Order ahead"}:
        return design_name
    return profile.display_name


def business_payload(item: BusinessProfile, *, display_name: str | None = None) -> dict:
    socials={key:("" if _fixture_customer_value(value) else value) for key,value in (item.socials or {}).items()}
    contact_email=None if _fixture_customer_value(item.contact_email) else item.contact_email
    return {"display_name":display_name or item.display_name,"legal_name":item.legal_name,"contact_email":contact_email,"phone":item.phone,"address":item.address or {},"socials":socials,"timezone":item.timezone,"currency":item.currency,"pickup_instructions":item.pickup_instructions,"fulfillment_wording":item.fulfillment_wording}

@router.get("/owner/business-profile")
def owner_business_profile(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.get(BusinessProfile, tenant.organization_id)
    if item is None:
        organization=session.get(Organization,tenant.organization_id)
        item=BusinessProfile(organization_id=tenant.organization_id,display_name=organization.name if organization else tenant.organization_slug)
        session.add(item);session.commit()
    return business_payload(item,display_name=_setup_customer_name(session,tenant.organization_id,item))

@router.put("/owner/business-profile")
def save_business_profile(payload: BusinessInput, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as error: raise HTTPException(422, detail="Choose a valid timezone.") from error
    item = session.get(BusinessProfile, tenant.organization_id)
    if item is None: item = BusinessProfile(organization_id=tenant.organization_id, display_name=payload.display_name); session.add(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value.strip() if isinstance(value, str) else value)
    workspace=DesignService(session,tenant).workspace(lock=True)
    if workspace.draft_config.get("displayName") != item.display_name:
        workspace.draft_config={**workspace.draft_config,"displayName":item.display_name}
        workspace.revision+=1;workspace.updated_by_user_id=principal.user_id
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="business_profile.updated",target_type="organization",target_id=str(tenant.organization_id),outcome="success"));session.commit()
    return business_payload(item)

@router.put("/owner/onboarding")
def save_onboarding(payload: OnboardingInput, _: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    item = session.scalar(select(OnboardingState).where(OnboardingState.organization_id == tenant.organization_id).with_for_update())
    if item is None: item=OnboardingState(organization_id=tenant.organization_id); session.add(item)
    readiness=evaluate_storefront_readiness(session,tenant.organization_id);derived_steps=onboarding_completed_steps(readiness)
    if item.revision != payload.revision:
        requested_state="complete" if item.initial_setup_completed_at is not None else "in_progress"
        if item.completed_steps==derived_steps and item.current_step==payload.current_step and item.state==requested_state:
            return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision}
        raise HTTPException(409, detail="Onboarding changed in another session.")
    allowed={"business","storefront","hours","fulfillment","design","catalog","clover","payments"}
    journey_steps={"welcome","look","brand","business","catalog","ordering","payments","preview","launch","complete"}
    if not set(payload.completed_steps)<=allowed or payload.current_step not in journey_steps|allowed: raise HTTPException(422,detail="Invalid onboarding checkpoint.")
    item.completed_steps=derived_steps; item.current_step=payload.current_step; item.revision+=1
    # Checklist state is progress UX only; public availability is authoritative data.
    item.state="complete" if item.initial_setup_completed_at is not None else "in_progress"
    organization=session.get(Organization,tenant.organization_id)
    synchronize_public_readiness(session, tenant.organization_id)
    session.commit(); return {"state":item.state,"currentStep":item.current_step,"completedSteps":item.completed_steps,"publicReady":item.public_ready,"revision":item.revision,"initialSetupCompletedAt":item.initial_setup_completed_at,"initialLaunchSource":item.initial_launch_source}


@router.post("/owner/launch")
def initial_launch(principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    onboarding = session.scalar(select(OnboardingState).where(OnboardingState.organization_id == tenant.organization_id).with_for_update())
    if onboarding is None:
        onboarding = OnboardingState(organization_id=tenant.organization_id, current_step="launch")
        session.add(onboarding); session.flush()
    if onboarding.initial_setup_completed_at is not None:
        result = synchronize_public_readiness(session, tenant.organization_id); session.commit()
        return {"launched":True,"initialSetupCompletedAt":onboarding.initial_setup_completed_at,"publicReady":result.public_ready}
    preflight = evaluate_storefront_readiness(session, tenant.organization_id)
    required = {key:value for key,value in preflight.checks.items() if key not in {"organization","published_design"}}
    if not all(required.values()):
        raise HTTPException(409, detail={"code":"storefront_not_ready","message":"Complete required setup before launch.","checks":required})
    workspace = DesignService(session, tenant).workspace()
    if workspace.published_version_id is None:
        try: DesignService(session, tenant).publish(principal.user_id)
        except DesignValidationError as error: raise HTTPException(422, detail={"code":"design_invalid","message":str(error)}) from error
    organization = session.get(Organization, tenant.organization_id)
    if organization is None: raise HTTPException(409, detail="Organization is unavailable.")
    organization.lifecycle_status = "active"
    result = synchronize_public_readiness(session, tenant.organization_id)
    if not result.public_ready:
        raise HTTPException(409, detail={"code":"storefront_not_ready","message":"Authoritative launch checks did not pass.","checks":result.checks})
    now = datetime.now(timezone.utc)
    onboarding.initial_setup_completed_at = now; onboarding.initial_launch_source = "owner"; onboarding.initial_launch_by_user_id = principal.user_id
    onboarding.state = "complete"; onboarding.current_step = "complete"; onboarding.completed_steps = onboarding_completed_steps(result); onboarding.public_ready = True; onboarding.revision += 1
    session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="merchant.initial_launch_completed",target_type="organization",target_id=str(tenant.organization_id),outcome="success",metadata_json={"source":"owner"}))
    session.commit()
    return {"launched":True,"initialSetupCompletedAt":now,"publicReady":True}

@router.get("/owner/entitlements")
def entitlements(tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    state,plan,features=entitlement_features(session,tenant.organization_id)
    return {"state":state,"plan":plan,"features":features}

@router.get("/owner/media")
def list_media(request: Request, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> list[dict]:
    rows=session.scalars(select(MediaAsset).where(MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active").order_by(MediaAsset.created_at.desc())).all()
    result=[]
    for item in rows:
        result.append({"id":str(item.id),"storageKey":item.storage_key,"mediaType":item.media_type,"purpose":item.purpose,"altText":item.alt_text,"byteSize":item.byte_size,"width":item.width,"height":item.height,"url":f"/api/v1/storefront/media/{item.id}","ownerUrl":f"/api/v1/owner/media/{item.id}/content"})
    return result

@router.get("/owner/starter-media")
def list_starter_media(collection: str = "cafe-restaurant", _: TenantContext = Depends(authenticated_owner_tenant)) -> dict:
    assets=[]
    for item in STARTER_MEDIA_ASSETS:
        if item.collection != collection: continue
        available=starter_asset_available(item)
        assets.append({
            "key":item.key,"name":item.name,"collection":item.collection,"category":item.category,
            "tags":list(item.tags),"width":item.width,"height":item.height,"active":item.active,
            "sortOrder":item.sort_order,"altText":item.alt_text,"assetVersion":item.version,
            "available":available,"reference":item.reference,
            "thumbnailUrl":f"/api/v1/storefront/starter-media/{item.collection}/{item.key}?version={item.version}" if available else None,
        })
    return {"manifestVersion":1,"collection":{"key":collection,"name":"Café & Restaurant"},"assets":assets}

@router.get("/storefront/starter-media/{collection}/{asset_key}")
def storefront_starter_media(collection: str, asset_key: str, version: int = 1) -> FileResponse:
    reference=starter_reference(collection,asset_key,version);item=next((asset for asset in STARTER_MEDIA_ASSETS if asset.reference==reference),None)
    if item is None: raise HTTPException(404,detail="Starter image not found.")
    path=starter_asset_path(item)
    if not path.is_file(): raise HTTPException(404,detail="Starter image is not available.")
    return FileResponse(path,media_type="image/webp",headers={"Cache-Control":"public, max-age=31536000, immutable"})

@router.post("/owner/media/upload", status_code=201)
async def upload_media(request: Request, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session), content_type: str = Header(alias="Content-Type"), alt_text: str = Header(default="",alias="X-Media-Alt"), purpose: str = Header(default="design", alias="X-Media-Purpose")) -> dict:
    if len(alt_text) > 300: raise HTTPException(422,detail="Alternative text is too long.")
    if purpose not in {"design","product"}: raise HTTPException(422,detail="Media purpose must be design or product.")
    data=await request.body(); media_id=uuid4()
    try:
        prepared=prepare_image(data,content_type)
        width,height=prepared.width,prepared.height
        if purpose == "product" and (width < 800 or height < 800): raise MediaValidationError("Product images must be at least 800 × 800 pixels.")
        storage=media_storage(request);storage_key,checksum=storage.put(tenant.organization_id,media_id,prepared.data,prepared.media_type)
    except MediaValidationError as error: raise HTTPException(422,detail=str(error)) from error
    except MediaStorageError as error: raise HTTPException(503,detail="Permanent media storage is unavailable.") from error
    item=MediaAsset(id=media_id,organization_id=tenant.organization_id,created_by_user_id=principal.user_id,storage_key=storage_key,media_type=prepared.media_type,purpose=purpose,alt_text=alt_text.strip(),byte_size=len(prepared.data),width=width,height=height,checksum=checksum)
    try:
        item.storage_key=storage_key;item.checksum=checksum;session.add(item);session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.uploaded",target_type="media_asset",target_id=str(item.id),outcome="success",metadata_json={"mediaType":item.media_type,"byteSize":item.byte_size}));session.commit()
    except Exception:
        session.rollback();storage.delete(storage_key);raise
    return {"id":str(item.id),"mediaType":item.media_type,"purpose":item.purpose,"altText":item.alt_text,"byteSize":item.byte_size,"width":width,"height":height,"url":f"/api/v1/storefront/media/{item.id}","ownerUrl":f"/api/v1/owner/media/{item.id}/content"}

@router.get("/storefront/media/{media_id}")
def storefront_media(media_id: UUID, request: Request, tenant: TenantContext = Depends(ladels_compatibility_tenant), session: Session = Depends(get_catalog_session)) -> FileResponse:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active"))
    if item is None: raise HTTPException(404,detail="Media not found.")
    try: content=media_storage(request).read(item.storage_key)
    except (MediaStorageError,MediaValidationError,OSError) as error: raise HTTPException(404,detail="Media not found.") from error
    return Response(content=content,media_type=item.media_type,headers={"Cache-Control":"public, max-age=31536000, immutable","Vary":"Host","X-Content-Type-Options":"nosniff"})

@router.get("/owner/media/{media_id}/content")
def owner_media(media_id: UUID, request: Request, tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> FileResponse:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id,MediaAsset.status=="active"))
    if item is None: raise HTTPException(404,detail="Media not found.")
    try: content=media_storage(request).read(item.storage_key)
    except (MediaStorageError,MediaValidationError,OSError) as error: raise HTTPException(404,detail="Media not found.") from error
    return Response(content=content,media_type=item.media_type,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@router.post("/owner/media", status_code=201)
def create_media(payload: MediaInput, request: Request, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> dict:
    allowed_prefixes=(f"{tenant.organization_id}/",f"tenants/{tenant.organization_id}/")
    if not payload.storage_key.startswith(allowed_prefixes): raise HTTPException(422,detail="Media storage key is outside this business.")
    try:
        stored_data=media_storage(request).read(payload.storage_key); prepared=prepare_image(stored_data,payload.media_type)
    except (MediaStorageError,MediaValidationError,OSError) as error: raise HTTPException(422,detail="Stored media could not be verified.") from error
    stored_checksum=hashlib.sha256(stored_data).hexdigest()
    if payload.byte_size!=len(stored_data) or payload.checksum!=stored_checksum: raise HTTPException(422,detail="Stored media metadata does not match the object.")
    item=MediaAsset(organization_id=tenant.organization_id,created_by_user_id=principal.user_id,storage_key=payload.storage_key,media_type=prepared.media_type,byte_size=len(stored_data),checksum=stored_checksum,alt_text=payload.alt_text,width=prepared.width,height=prepared.height)
    session.add(item);session.flush();session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.created",target_type="media_asset",target_id=str(item.id),outcome="success"));session.commit()
    return {"id":str(item.id)}

@router.delete("/owner/media/{media_id}", status_code=204)
def archive_media(media_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), tenant: TenantContext = Depends(authenticated_owner_tenant), session: Session = Depends(get_catalog_session)) -> Response:
    item=session.scalar(select(MediaAsset).where(MediaAsset.id==media_id,MediaAsset.organization_id==tenant.organization_id))
    if item is None: raise HTTPException(404,detail="Media not found.")
    referenced=session.scalar(select(DesignMediaReference.id).where(DesignMediaReference.organization_id==tenant.organization_id,DesignMediaReference.media_asset_id==media_id).limit(1))
    if referenced is not None: raise HTTPException(409,detail="This image is used by a published design.")
    product_reference=f"/api/v1/storefront/media/{media_id}"
    if session.scalar(select(Product.id).where(Product.organization_id==tenant.organization_id,Product.media_asset_id==media_id).limit(1)) is not None: raise HTTPException(409,detail="This image is used by a product.")
    item.status="archived";session.add(OperationalAuditEvent(organization_id=tenant.organization_id,scope="tenant",actor_user_id=principal.user_id,action="media.archived",target_type="media_asset",target_id=str(item.id),outcome="success"));session.commit();return Response(status_code=204)

@router.get("/platform/admin/organizations")
def platform_organizations(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> list[dict]:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.read",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform access is not authorized."})
    rows=session.execute(select(Organization,OnboardingState,DesignWorkspace,OrganizationSubscription).outerjoin(OnboardingState,OnboardingState.organization_id==Organization.id).outerjoin(DesignWorkspace,DesignWorkspace.organization_id==Organization.id).outerjoin(OrganizationSubscription,OrganizationSubscription.organization_id==Organization.id).order_by(Organization.name)).all()
    session.add(OperationalAuditEvent(scope="platform",actor_user_id=principal.user_id,action="platform.organizations_viewed",outcome="success",metadata_json={"count":len(rows)}));session.commit()
    result=[]
    for org,onboarding,design,subscription in rows:
        hostname=session.scalar(select(StorefrontHostname.hostname).where(StorefrontHostname.organization_id==org.id,StorefrontHostname.is_canonical.is_(True),StorefrontHostname.status=="verified"))
        owners=session.scalar(select(func.count()).select_from(Membership).join(Role,Role.id==Membership.role_id).where(Membership.organization_id==org.id,Membership.status=="active",Role.key=="owner"))
        clover=session.scalars(select(CloverInstallation.connection_state).where(CloverInstallation.organization_id==org.id)).all()
        result.append({"id":str(org.id),"name":org.name,"slug":org.slug,"status":org.lifecycle_status,"onboarding":onboarding.state if onboarding else "not_started","publicReady":bool(onboarding and onboarding.public_ready),"canonicalHost":hostname,"ownerMemberships":owners or 0,"cloverHealth":sorted(set(clover)) or ["not_connected"],"publishedVersionId":str(design.published_version_id) if design and design.published_version_id else None,"subscription":subscription.state if subscription else "none"})
    return result

@router.get("/platform/admin/organizations/{organization_id}")
def platform_organization_detail(organization_id: UUID, principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.read",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform access is not authorized."})
    organization=session.get(Organization,organization_id)
    if organization is None: raise HTTPException(404,detail="Organization not found.")
    readiness=evaluate_storefront_readiness(session,organization_id)
    hostnames=session.scalars(select(StorefrontHostname).where(StorefrontHostname.organization_id==organization_id).order_by(StorefrontHostname.created_at.desc())).all()
    audits=session.scalars(select(OperationalAuditEvent).where(OperationalAuditEvent.organization_id==organization_id).order_by(OperationalAuditEvent.occurred_at.desc()).limit(50)).all()
    owners=session.execute(select(Membership,JdsUser,Role).join(JdsUser,JdsUser.id==Membership.user_id).join(Role,Role.id==Membership.role_id).where(Membership.organization_id==organization_id,Role.key=="owner").order_by(JdsUser.display_name)).all()
    installations=session.scalars(select(CloverInstallation).where(CloverInstallation.organization_id==organization_id).order_by(CloverInstallation.created_at.desc())).all()
    workspace=session.get(DesignWorkspace,organization_id);subscription=session.get(OrganizationSubscription,organization_id)
    warnings=[]
    if not owners: warnings.append("No owner membership is assigned.")
    if not any(item.status=="verified" and item.is_canonical for item in hostnames): warnings.append("No verified canonical storefront is configured.")
    if not installations or not any(item.connection_state=="connected" for item in installations): warnings.append("Clover is not connected.")
    if workspace is None or workspace.published_version_id is None: warnings.append("No storefront design is published.")
    if subscription is None: warnings.append("No subscription record is assigned.")
    result={"id":str(organization.id),"name":organization.name,"slug":organization.slug,"status":organization.lifecycle_status,"readiness":{"publicReady":readiness.public_ready,"checks":readiness.checks},"hostnames":[{"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":item.is_canonical} for item in hostnames],"owners":[{"membershipId":str(membership.id),"displayName":user.display_name,"email":user.primary_email,"status":membership.status} for membership,user,_ in owners],"clover":[{"environment":item.environment,"connectionState":item.connection_state,"merchantReference":item.merchant_id[-4:].rjust(len(item.merchant_id),"•") if item.merchant_id else None,"updatedAt":item.updated_at} for item in installations],"design":{"publishedVersionId":str(workspace.published_version_id) if workspace and workspace.published_version_id else None,"draftRevision":workspace.revision if workspace else None},"subscription":{"state":subscription.state,"plan":subscription.plan_key,"provider":subscription.provider} if subscription else None,"warnings":warnings,"audit":[{"action":item.action,"outcome":item.outcome,"targetType":item.target_type,"targetId":item.target_id,"occurredAt":item.occurred_at} for item in audits]}
    session.add(OperationalAuditEvent(scope="platform",actor_user_id=principal.user_id,action="platform.organization_viewed",target_type="organization",target_id=str(organization_id),outcome="success"));session.commit()
    return result

@router.get("/owner/platform-capabilities")
def platform_capabilities(principal: AuthPrincipal = Depends(current_principal), session: Session = Depends(get_catalog_session)) -> dict:
    capabilities = session.scalars(select(PlatformGrant.capability).where(
        PlatformGrant.user_id == principal.user_id,
        PlatformGrant.is_active.is_(True),
    ).order_by(PlatformGrant.capability)).all()
    return {"capabilities": capabilities}

@router.post("/platform/admin/organizations", status_code=201)
def provision_organization(payload: ProvisionOrganizationInput, principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session), request: Request = None) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.write",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform provisioning is not authorized."})
    try:
        settings = request.app.state.auth_settings if request is not None else AuthSettings.from_env()
        provisioned = MerchantAcquisitionService(session, settings).provision(AcquisitionRequest(slug=payload.slug,display_name=payload.display_name,owner_email=payload.owner_email,source=payload.acquisition_source,requested_plan_key=payload.requested_plan_key,external_installation_reference=payload.external_installation_reference,verified_merchant_reference=payload.verified_merchant_reference,provider_metadata=payload.provider_metadata),now=datetime.now(timezone.utc),actor_user_id=principal.user_id)
    except AcquisitionError as error:
        raise HTTPException(409,detail={"code":"provisioning_failed","message":str(error)}) from error
    session.commit()
    return {"id":str(provisioned.acquisition.organization_id),"slug":payload.slug,"status":"onboarding","activationStatus":"pending","activationPath":f"/activate#{provisioned.activation_secret}","publicReady":False}

@router.post("/platform/admin/hostnames/{hostname_id}/verify")
def verify_hostname(hostname_id: UUID, principal: AuthPrincipal = Depends(csrf_principal), session: Session = Depends(get_catalog_session)) -> dict:
    grant=session.scalar(select(PlatformGrant.id).where(PlatformGrant.user_id==principal.user_id,PlatformGrant.capability=="platform.organizations.write",PlatformGrant.is_active.is_(True)))
    if grant is None: raise HTTPException(403,detail={"code":"platform_access_required","message":"Platform hostname verification is not authorized."})
    item=session.get(StorefrontHostname,hostname_id)
    if item is None or item.status=="disabled": raise HTTPException(404,detail="Hostname not found.")
    session.execute(StorefrontHostname.__table__.update().where(StorefrontHostname.organization_id==item.organization_id,StorefrontHostname.id!=item.id).values(is_canonical=False))
    item.status="verified";item.is_canonical=True;item.verified_at=datetime.now(timezone.utc)
    result=synchronize_public_readiness(session,item.organization_id)
    session.add(OperationalAuditEvent(organization_id=item.organization_id,scope="platform",actor_user_id=principal.user_id,action="storefront.hostname_verified",target_type="storefront_hostname",target_id=str(item.id),outcome="success",metadata_json={"hostname":item.hostname}));session.commit()
    return {"id":str(item.id),"hostname":item.hostname,"status":item.status,"canonical":True,"publicReady":result.public_ready}
