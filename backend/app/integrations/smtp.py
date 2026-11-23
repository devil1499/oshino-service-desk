import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SmtpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.smtp",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_security: Literal["ssl", "starttls"]
    smtp_username: str = Field(min_length=1)
    smtp_password: SecretStr = Field(min_length=1)
    smtp_from: EmailStr
    smtp_test_recipients: str = Field(min_length=1)

    @field_validator("smtp_test_recipients")
    @classmethod
    def valid_recipients(cls, value):
        TypeAdapter(list[EmailStr]).validate_python([part.strip() for part in value.split(",")])
        return value

    def allowed(self, recipient: str) -> bool:
        return recipient.casefold() in {
            part.strip().casefold() for part in self.smtp_test_recipients.split(",")
        }


class DeliveryRejected(RuntimeError):
    """SMTP 明确拒绝，本次未被接受。"""


class DeliveryUnknown(RuntimeError):
    """发送结果无法确定，不得自动重发。"""


def deliver(config: SmtpSettings, body: dict) -> None:
    message = EmailMessage()
    message["From"] = str(config.smtp_from)
    message["To"] = body["recipient"]
    message["Subject"] = body["subject"]
    message["Message-ID"] = body["message_id"]
    message["Date"] = format_datetime(datetime.now(UTC))
    message.set_content(body["content"])
    client = None
    try:
        context = ssl.create_default_context()
        if config.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(
                config.smtp_host, config.smtp_port, timeout=15, context=context
            )
        else:
            client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
            client.starttls(context=context)
        client.login(config.smtp_username, config.smtp_password.get_secret_value())
        client.send_message(message, from_addr=str(config.smtp_from), to_addrs=[body["recipient"]])
    except smtplib.SMTPAuthenticationError as error:
        raise DeliveryRejected("SMTP 认证失败，请检查授权码和账号") from error
    except smtplib.SMTPRecipientsRefused as error:
        raise DeliveryRejected("SMTP 拒绝收件人") from error
    except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as error:
        raise DeliveryRejected(f"SMTP 明确拒绝发送，代码 {error.smtp_code}") from error
    except smtplib.SMTPNotSupportedError as error:
        raise DeliveryRejected("SMTP 服务不支持所配置的安全连接或认证方式") from error
    except (OSError, smtplib.SMTPException) as error:
        # 连接中断可能发生在服务器已经接受邮件之后，不能当作可重试失败。
        raise DeliveryUnknown(
            "邮件连接异常，无法确认 SMTP 是否接受；请核查邮箱和服务端记录"
        ) from error
    finally:
        if client is not None:
            client.close()
