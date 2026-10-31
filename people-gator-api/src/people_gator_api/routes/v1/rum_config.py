"""Public browser-monitoring configuration, independent of app initialization."""
from fastapi import APIRouter, Response

from people_gator_api.settings import settings

router = APIRouter(include_in_schema=False)


@router.get("/rum-config")
async def rum_config(response: Response):
    # Runtime browser configuration is deliberately public. Never serialize
    # Settings or exporter headers here; only publish the dedicated RUM token.
    response.headers["Cache-Control"] = "no-store"
    if not settings.rum.enabled:
        return {"enabled": False}
    rum = settings.rum
    deployment = settings.deployment
    return {
        "enabled": True,
        "clientToken": rum.client_token.get_secret_value(),
        "site": rum.site,
        "organizationIdentifier": rum.organization_identifier,
        "applicationId": rum.application_id,
        "service": "people-gator-app",
        "env": deployment.environment,
        "version": deployment.version,
        "sessionSampleRate": rum.session_sample_rate,
        "sessionReplaySampleRate": rum.session_replay_sample_rate,
        "context": {"commit": deployment.commit, "pr_number": deployment.pr_number},
    }

