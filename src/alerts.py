"""Slack alerts. Stub: thirawatv-sketch fills in the bodies, keep these signatures (see GUIDE.md, contract A)."""


def send_alert(title: str, detail: str = '') -> None:
    print(f'[ALERT] {title} {detail}')


def notify_validation_failure(detail: str, payload: dict | None = None) -> None:
    send_alert('Invalid prediction request rejected', detail)
