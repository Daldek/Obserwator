"""
Security headers shared by the two servers: ``obserwator server`` and ``obserwator gui serve``.

`PERMISSIONS_POLICY` denies the powerful browser features neither the GUI nor the REST
API's documentation uses (the GUI's map, charts and downloads need none of them; the
clipboard stays allowed for the hand-off of ``nogat-handoff.js``) and the Topics API.
Only features that Chromium on Linux knows are named: an unknown one (``bluetooth``,
``web-share``) is a console warning on every page. `REFERRER_POLICY` sends no
``Referer`` at all, so the basemap's tile server and a linked site learn no page of the
server.
"""

__all__ = ["PERMISSIONS_POLICY", "REFERRER_POLICY", "security_headers"]

_UNUSED_FEATURES = (
    "accelerometer",
    "autoplay",
    "browsing-topics",
    "camera",
    "display-capture",
    "encrypted-media",
    "fullscreen",
    "geolocation",
    "gyroscope",
    "hid",
    "idle-detection",
    "local-fonts",
    "magnetometer",
    "microphone",
    "midi",
    "payment",
    "picture-in-picture",
    "publickey-credentials-get",
    "screen-wake-lock",
    "serial",
    "usb",
    "xr-spatial-tracking",
)

PERMISSIONS_POLICY = ", ".join(f"{feature}=()" for feature in _UNUSED_FEATURES)
"""``Permissions-Policy``: every unused feature denied to the page and its frames."""

REFERRER_POLICY = "no-referrer"
"""``Referrer-Policy``: no ``Referer`` on any request of a page."""


def security_headers() -> list[tuple[bytes, bytes]]:
    """
    The security headers both servers put on every answer.

    Returns
    -------
    list of tuple of (bytes, bytes)
        ``X-Content-Type-Options: nosniff``, `REFERRER_POLICY` and
        `PERMISSIONS_POLICY` as ASGI header pairs (lower-case names).
    """
    return [
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", REFERRER_POLICY.encode()),
        (b"permissions-policy", PERMISSIONS_POLICY.encode()),
    ]
