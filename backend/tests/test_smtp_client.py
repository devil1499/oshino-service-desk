from app.integrations import smtp


def test_smtp_message_is_sent_to_the_confirmed_test_address(monkeypatch):
    calls = []

    class FakeConnection:
        def __init__(self, host, port, *, timeout, context):
            calls.append(("connect", host, port, timeout))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message, *, from_addr, to_addrs):
            calls.append(("send", message["Subject"], from_addr, to_addrs, message.get_content().strip()))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(smtp.smtplib, "SMTP_SSL", FakeConnection)
    config = smtp.SmtpSettings.model_validate({
        "smtp_host": "smtp.example.com",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "smtp_username": "sender@example.com",
        "smtp_password": "test-authorization-code",
        "smtp_from": "sender@example.com",
        "smtp_test_recipients": "inbox@example.com",
    })
    smtp.deliver(config, {
        "recipient": "inbox@example.com",
        "subject": "处理说明",
        "content": "请核对登录状态。",
        "message_id": "<test-id@example.com>",
    })

    assert calls[0] == ("connect", "smtp.example.com", 465, 15)
    assert calls[1] == ("login", "sender@example.com", "test-authorization-code")
    assert calls[2] == ("send", "处理说明", "sender@example.com", ["inbox@example.com"], "请核对登录状态。")
    assert calls[3] == ("close",)
