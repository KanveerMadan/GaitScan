"""Error tracking. Sentry is initialised only when SENTRY_DSN is set."""
import sentry_sdk


def init_sentry(dsn: str, environment: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,          # no user IPs, cookies or headers with identifiers
        max_request_body_size="never",   # never send uploads or login bodies
        traces_sample_rate=0.0,
    )
