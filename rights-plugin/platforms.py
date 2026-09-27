"""Which Hermes messaging platforms are configured on this deployment.

Mirrors, by hand, the exact (label -> token env var) mapping Hermes core's
own ``hermes status`` command uses to decide "configured" vs "not
configured" for its "Messaging Platforms" section (``hermes_cli/status.py``
— verified by reading that file directly on ``test-server``, see
``.agents/DECISIONS.md``, 2026-08-17). Not imported from Hermes core: this
repo doesn't vendor Hermes, and a plugin process isn't guaranteed to have
``hermes_cli`` importable — a hand-kept copy of the mapping instead.

"Configured" here means "credentials are set in the environment" (the same
definition ``hermes status`` uses), not "currently connected" — this plugin
has no way to check a live adapter connection from inside a plugin process.
Good enough to decide which platforms make sense to offer in the
dashboard's role-binding picker (see ``dashboard/dist/index.js``): no point
proposing "Telegram" if ``TELEGRAM_BOT_TOKEN`` was never set.

Only the ``"slack"`` slug is verified against something real (every
``RoleBinding.platform``/session ``source`` value this repo has ever
actually produced). The other slugs are a reasonable lower-snake-case guess
derived from Hermes's own label — worth double-checking against a real
session's ``source`` field before trusting one blindly if a second platform
is ever wired up on this deployment.
"""

from __future__ import annotations

import os
from typing import Any

# (label, token env var Hermes checks for "configured", our best-guess slug)
_KNOWN_PLATFORMS: list[tuple[str, str, str]] = [
    ("Telegram", "TELEGRAM_BOT_TOKEN", "telegram"),
    ("Discord", "DISCORD_BOT_TOKEN", "discord"),
    ("WhatsApp", "WHATSAPP_ENABLED", "whatsapp"),
    ("Signal", "SIGNAL_HTTP_URL", "signal"),
    ("Slack", "SLACK_BOT_TOKEN", "slack"),
    ("Email", "EMAIL_ADDRESS", "email"),
    ("SMS", "TWILIO_ACCOUNT_SID", "sms"),
    ("DingTalk", "DINGTALK_CLIENT_ID", "dingtalk"),
    ("Feishu", "FEISHU_APP_ID", "feishu"),
    ("WeCom", "WECOM_BOT_ID", "wecom"),
    ("WeCom Callback", "WECOM_CALLBACK_CORP_ID", "wecom_callback"),
    ("Weixin", "WEIXIN_ACCOUNT_ID", "weixin"),
    ("BlueBubbles", "BLUEBUBBLES_SERVER_URL", "bluebubbles"),
    ("QQBot", "QQ_APP_ID", "qqbot"),
    ("Yuanbao", "YUANBAO_APP_ID", "yuanbao"),
]


def all_platforms() -> list[dict[str, Any]]:
    """Every platform Hermes core knows about, each flagged with whether it
    looks configured on this deployment."""
    return [
        {"slug": slug, "label": label, "configured": bool(os.environ.get(token_var))}
        for label, token_var, slug in _KNOWN_PLATFORMS
    ]


def connected_platforms() -> list[dict[str, Any]]:
    """Just the subset that looks configured — what the dashboard's
    role-binding form actually offers as pick-list options."""
    return [p for p in all_platforms() if p["configured"]]
