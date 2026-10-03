"""Best-effort Slack alerts using the caller-facing contract in GUIDE.md."""

import json
import os
from pathlib import Path
from urllib import request

_MAX_DETAIL_LENGTH = 1000
_TIMEOUT_SECONDS = 3


def _write_local_alert(title: str, detail: str) -> None:
    """Try stdout and the log independently; neither may break the caller."""
    message = f'[ALERT] {title}\n{detail}'
    try:
        print(message)
    except Exception:
        pass

    try:
        log_path = Path('logs') / 'alerts.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a', encoding='utf-8') as log_file:
            log_file.write(message + '\n')
    except Exception:
        pass


def send_alert(title: str, detail: str = '') -> None:
    """Send to Slack, or keep a local alert if delivery is unavailable."""
    safe_title = 'Alert'
    safe_detail = ''
    try:
        safe_title = str(title)
        safe_detail = str(detail)[:_MAX_DETAIL_LENGTH]
        webhook_url = os.environ.get('SLACK_WEBHOOK_URL', '').strip()
        if not webhook_url:
            _write_local_alert(safe_title, safe_detail)
            return

        body = json.dumps(
            {'text': f'*{safe_title}*\n{safe_detail}'}, ensure_ascii=False
        ).encode('utf-8')
        slack_request = request.Request(
            webhook_url,
            data=body,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        with request.urlopen(slack_request, timeout=_TIMEOUT_SECONDS):
            pass
    except Exception as error:
        # Exception messages can contain the secret URL; log only the type.
        _write_local_alert(
            safe_title,
            f'{safe_detail}\n[Slack delivery failed: {type(error).__name__}]',
        )


def notify_validation_failure(detail: str, payload: dict | None = None) -> None:
    """Include the validation detail and a short preview of the bad payload."""
    safe_detail = ''
    try:
        # Reserve room for the payload so long validation errors do not hide it.
        safe_detail = str(detail)[:700]
        if payload is not None:
            payload_text = json.dumps(payload, ensure_ascii=False, default=str)
            safe_detail += f'\nPayload: {payload_text[:280]}'
    except Exception as error:
        safe_detail += f'\n[Alert formatting failed: {type(error).__name__}]'

    send_alert('Invalid prediction request rejected', safe_detail)
