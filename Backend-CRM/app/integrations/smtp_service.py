"""
SMTP Service for sending emails from CRM
Sends emails using SMTP (Gmail, SendGrid, or custom SMTP server)
"""
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Union
import os
import re

import aiofiles

from app.config import settings


class SMTPService:
    """Service for sending emails via SMTP (Mailgun, Gmail, etc.)"""
    
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None
    ):
        # Prefer explicit args, then settings, then sensible defaults
        self.smtp_host = smtp_host or getattr(settings, "smtp_host", "smtp.gmail.com")
        self.smtp_port = smtp_port or getattr(settings, "smtp_port", 587)
        self.smtp_user = smtp_user or getattr(settings, "smtp_user", None)
        self.smtp_password = smtp_password or getattr(settings, "smtp_password", None)
        
        # Log SMTP configuration status
        if self.smtp_user and self.smtp_password:
            print(f"✅ SMTP configured: {self.smtp_user}@{self.smtp_host}:{self.smtp_port}")
        else:
            print(f"⚠️  SMTP not fully configured - missing credentials (host: {self.smtp_host}:{self.smtp_port})")
    
    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        from_email: str,
        from_name: Optional[str] = None,
        html: bool = False,
        attachments: Optional[List[str]] = None,
        reply_to: Optional[str] = None
    ) -> dict:
        """
        Send an email via SMTP
        
        Args:
            to: Recipient email address(es) - can be a single string or list of strings
            subject: Email subject
            body: Email body (plain text or HTML)
            from_email: Sender email address (e.g., study1site1@dizzaroo.com)
            from_name: Sender display name
            html: Whether body is HTML
            attachments: List of file paths to attach
            reply_to: Reply-To email address
        
        Returns:
            Dict with success status and message ID
        """
        try:
            # ------------------------------------------------------------------
            # Sanitize from_email to ALWAYS be a valid RFC-compliant address.
            # This protects us even if upstream passes something like "New study01@mg.dizzaroo.com".
            # ------------------------------------------------------------------
            raw_from_email = (from_email or "").strip()
            if "@" in raw_from_email:
                local_part, domain_part = raw_from_email.split("@", 1)
            else:
                # Fallback to configured SMTP domain if no domain provided
                local_part = raw_from_email or "noreply"
                smtp_user = settings.smtp_user or ""
                domain_part = smtp_user.split("@")[1] if "@" in smtp_user else "dizzaroo.com"

            # Normalize local part: lowercase, remove anything except letters, digits and hyphens
            safe_local = re.sub(r"[^a-z0-9-]+", "", local_part.lower())
            if not safe_local:
                safe_local = "noreply"

            sanitized_from_email = f"{safe_local}@{domain_part}"

            # Normalize to list of recipients
            if isinstance(to, str):
                recipient_list = [to]
            else:
                recipient_list = [email.strip() for email in to if email and email.strip()]
            
            if not recipient_list:
                return {
                    'success': False,
                    'error': 'No valid recipient email addresses provided',
                    'method': 'smtp'
                }
            
            # Create message
            msg = MIMEMultipart()
            # Set To header as comma-separated string for multiple recipients
            msg['To'] = ', '.join(recipient_list)
            msg['Subject'] = subject
            
            if from_name:
                msg['From'] = f"{from_name} <{sanitized_from_email}>"
            else:
                msg['From'] = sanitized_from_email
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Add body
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Add attachments
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as f:
                            payload = f.read()
                        if filename.lower().endswith(".pdf"):
                            part = MIMEBase("application", "pdf")
                        else:
                            part = MIMEBase("application", "octet-stream")
                        part.set_payload(payload)
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", "attachment", filename=filename)
                        msg.attach(part)
            
            # Send via SMTP
            if self.smtp_user and self.smtp_password:
                print(f"📧 Attempting to send email via SMTP ({self.smtp_host}:{self.smtp_port})")
                print(f"   From: {sanitized_from_email}")
                print(f"   To: {', '.join(recipient_list)}")
                print(f"   Recipient count: {len(recipient_list)}")
                print(f"   Recipient list: {recipient_list}")
                print(f"   Subject: {subject}")
                
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    print("   Connected to SMTP server")
                    server.starttls()
                    print("   TLS started")
                    server.login(self.smtp_user, self.smtp_password)
                    print(f"   Authenticated as {self.smtp_user}")
                    # Use send_message with to_addrs parameter for proper delivery to all recipients
                    # to_addrs can be a list of email addresses
                    server.send_message(msg, to_addrs=recipient_list)
                    print(f"   Message sent successfully to {len(recipient_list)} recipient(s)")
                
                print(f"✅ Email sent via SMTP to {len(recipient_list)} recipient(s): {', '.join(recipient_list)}")
                return {
                    'success': True,
                    'message_id': msg.get('Message-ID'),
                    'method': 'smtp',
                    'recipients': recipient_list
                }
            else:
                print(f"⚠️  SMTP credentials not configured, email not sent: {', '.join(recipient_list)}")
                return {
                    'success': False,
                    'error': 'SMTP credentials not configured',
                    'method': 'smtp'
                }
            
        except Exception as e:
            print(f'❌ SMTP error: {e}')
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'method': 'smtp',
                'recipients': recipient_list if 'recipient_list' in locals() else []
            }

    async def send_email_async(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        from_email: str,
        from_name: Optional[str] = None,
        html: bool = False,
        attachments: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """Async version of send_email — uses aiosmtplib + aiofiles so the
        FastAPI event loop is NOT blocked during the SMTP handshake.

        When to use this
        ----------------
        Routes where the user is **waiting in-flow** for a yes/no answer —
        OTP send/resend, signing-invite send. These must report
        success/failure synchronously to the user, so they can't be fired
        off to Celery as fire-and-forget; but the sync `send_email` was
        pinning the event loop for ~1-5s per request.

        For background notifications (monitoring letters, feasibility
        confirmations, etc.) use `enqueue_email()` instead — fully async
        via Celery with automatic retry, no event-loop cost at all.

        Returns the same dict shape as the sync `send_email`:
            {"success": bool, "error"?: str, "message_id"?: str,
             "recipients": list[str], "method": "smtp"}
        so callers can keep their existing `result.get("success")` checks
        unchanged.
        """
        # Lazy import so the app boots even if aiosmtplib isn't installed
        # in a particular environment (Celery-only image, scripts, …).
        try:
            import aiosmtplib  # noqa: F401
        except ImportError:
            print("⚠️  aiosmtplib not installed; using sync SMTP via thread pool")
            return await asyncio.to_thread(
                self.send_email,
                to=to,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
                html=html,
                attachments=attachments,
                reply_to=reply_to,
            )

        try:
            # MIME building is CPU-only; the sync path does the same work
            # and it's fast enough to inline. Reuse the same sanitization
            # logic so both paths behave identically.
            raw_from_email = (from_email or "").strip()
            if "@" in raw_from_email:
                local_part, domain_part = raw_from_email.split("@", 1)
            else:
                local_part = raw_from_email or "noreply"
                smtp_user = settings.smtp_user or ""
                domain_part = smtp_user.split("@")[1] if "@" in smtp_user else "dizzaroo.com"
            safe_local = re.sub(r"[^a-z0-9-]+", "", local_part.lower())
            if not safe_local:
                safe_local = "noreply"
            sanitized_from_email = f"{safe_local}@{domain_part}"

            if isinstance(to, str):
                recipient_list = [to]
            else:
                recipient_list = [e.strip() for e in to if e and e.strip()]
            if not recipient_list:
                return {
                    'success': False,
                    'error': 'No valid recipient email addresses provided',
                    'method': 'smtp',
                }

            msg = MIMEMultipart()
            msg['To'] = ', '.join(recipient_list)
            msg['Subject'] = subject
            if from_name:
                msg['From'] = f"{from_name} <{sanitized_from_email}>"
            else:
                msg['From'] = sanitized_from_email
            if reply_to:
                msg['Reply-To'] = reply_to
            msg.attach(MIMEText(body, 'html' if html else 'plain'))

            # Read attachments asynchronously — large files no longer pin
            # the event loop on disk I/O.
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        async with aiofiles.open(file_path, 'rb') as f:
                            payload = await f.read()
                        if filename.lower().endswith(".pdf"):
                            part = MIMEBase("application", "pdf")
                        else:
                            part = MIMEBase("application", "octet-stream")
                        part.set_payload(payload)
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", "attachment", filename=filename)
                        msg.attach(part)

            if not (self.smtp_user and self.smtp_password):
                print(
                    f"⚠️  SMTP credentials not configured, email not sent: "
                    f"{', '.join(recipient_list)}"
                )
                return {
                    'success': False,
                    'error': 'SMTP credentials not configured',
                    'method': 'smtp',
                }

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
                timeout=30,
            )
            print(
                f"✅ Email sent via aiosmtplib to {len(recipient_list)} "
                f"recipient(s): {', '.join(recipient_list)}"
            )
            return {
                'success': True,
                'message_id': msg.get('Message-ID'),
                'method': 'smtp',
                'recipients': recipient_list,
            }
        except Exception as e:
            print(f'❌ aiosmtplib error: {e}')
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'method': 'smtp',
                'recipients': recipient_list if 'recipient_list' in locals() else [],
            }


# Create default instance
smtp_service = SMTPService()


# ---------------------------------------------------------------------------
# Fire-and-forget enqueue helper
# ---------------------------------------------------------------------------
# Every direct call to `smtp_service.send_email(...)` from an `async def`
# route blocks the FastAPI event loop for the duration of the SMTP handshake
# (TLS negotiate + login + send), typically 1-5 seconds per email. Under any
# concurrency this serializes the entire worker.
#
# `enqueue_email(...)` pushes the send onto the Celery queue (see
# `app/workers/tasks.py::send_email_task`) and returns immediately with the
# Celery task id. The route can finish in milliseconds and return its 200/202
# response while the worker handles the slow part.
#
# Migration recipe — to convert a route that does:
#
#     result = smtp_service.send_email(
#         to=user.email, subject="…", body=html, from_email="…", html=True,
#     )
#     if not result.get("success"):
#         # error handling …
#
# Replace with:
#
#     from app.integrations.smtp_service import enqueue_email
#     enqueue_email(
#         to=user.email, subject="…", body=html, from_email="…", html=True,
#     )
#     # no error handling needed — worker retries + logs on failure
#
# Routes that **need** to observe the send result synchronously (e.g. an OTP
# challenge where the user is waiting in-flow) should keep calling
# `smtp_service.send_email(...)` directly for now; those are a small minority
# and a future task may move them onto an async path with a webhook-on-send.
def enqueue_email(
    to,
    subject: str,
    body: str,
    from_email: str,
    from_name: Optional[str] = None,
    html: bool = False,
    attachments: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
) -> Optional[str]:
    """Enqueue an outbound email for asynchronous delivery.

    Returns the Celery task id if the broker accepted the enqueue, else None.
    Never raises into the caller — broker outages must not break the request
    that triggered the email.
    """
    try:
        # Imported lazily so this module is safe to import in environments
        # where Celery / Redis aren't available (e.g. unit tests). The
        # send_email_task itself imports smtp_service lazily for the same
        # reason, breaking what would otherwise be a circular import.
        from app.workers.tasks import send_email_task

        async_result = send_email_task.delay(
            to=to,
            subject=subject,
            body=body,
            from_email=from_email,
            from_name=from_name,
            html=html,
            attachments=attachments,
            reply_to=reply_to,
        )
        return getattr(async_result, "id", None)
    except Exception as exc:
        # Last-resort fallback: send synchronously rather than silently
        # dropping the email when the broker is unreachable. This keeps the
        # existing behavior in dev environments where the worker isn't
        # running, while still giving prod the async fast path.
        print(f"⚠️  enqueue_email: broker enqueue failed ({exc}); sending inline as fallback")
        try:
            smtp_service.send_email(
                to=to,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
                html=html,
                attachments=attachments,
                reply_to=reply_to,
            )
        except Exception as send_exc:
            print(f"❌ enqueue_email: inline fallback also failed: {send_exc}")
        return None

