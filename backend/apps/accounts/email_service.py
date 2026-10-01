"""
Email service for Too Fresh To Waste.

Supports:
  - Resend (preferred)
  - SendGrid (fallback)
  - Django's built-in SMTP (dev/fallback)

Configure via environment variables:
  EMAIL_PROVIDER=resend|sendgrid|smtp
  EMAIL_API_KEY=your-api-key
  EMAIL_FROM=noreply@toofreshtowaste.in
  FRONTEND_URL=https://toofreshtowaste.in   (for generating email links)
"""

import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://127.0.0.1:5500')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'Too Fresh To Waste <noreply@toofreshtowaste.in>')
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'smtp')
EMAIL_API_KEY = os.getenv('EMAIL_API_KEY', '')


# ─── HTML email templates ──────────────────────────────────────────────────────

def _base_email_html(title: str, preheader: str, body_html: str) -> str:
    """Wraps content in a professional, TFTW-branded email template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <style>
    body {{ margin:0; padding:0; background:#F8FAFC; font-family:'Segoe UI',Arial,sans-serif; }}
    .wrapper {{ max-width:580px; margin:0 auto; padding:32px 16px; }}
    .card {{ background:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
    .header {{ background:linear-gradient(135deg,#FF788D 0%,#F45F78 100%); padding:36px 40px; text-align:center; }}
    .logo-text {{ color:#ffffff; font-size:1.3rem; font-weight:800; letter-spacing:-0.02em; }}
    .tagline {{ color:rgba(255,255,255,0.75); font-size:0.8rem; margin-top:4px; }}
    .body {{ padding:40px; }}
    .body h2 {{ color:#1E293B; font-size:1.4rem; font-weight:800; margin:0 0 12px; }}
    .body p {{ color:#475569; line-height:1.7; margin:0 0 18px; font-size:0.95rem; }}
    .btn {{ display:inline-block; background:linear-gradient(135deg,#FF788D,#F45F78); color:#ffffff !important;
            padding:14px 32px; border-radius:10px; text-decoration:none; font-weight:700;
            font-size:1rem; margin:8px 0 24px; letter-spacing:0.01em; }}
    .divider {{ border:none; border-top:1px solid #E2E8F0; margin:24px 0; }}
    .link-fallback {{ background:#F1F5F9; border-radius:8px; padding:12px 16px;
                      font-size:0.8rem; color:#64748B; word-break:break-all; margin-bottom:18px; }}
    .footer {{ padding:24px 40px; background:#F8FAFC; text-align:center;
               color:#94A3B8; font-size:0.78rem; line-height:1.6; }}
    .preheader {{ display:none; max-height:0; overflow:hidden; }}
  </style>
</head>
<body>
  <span class="preheader">{preheader}</span>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <div class="logo-text">🌱 Too Fresh To Waste</div>
        <div class="tagline">Save Food · Save Money · Save the Planet</div>
      </div>
      <div class="body">
        {body_html}
      </div>
      <div class="footer">
        <p>Too Fresh To Waste · Chandigarh, India</p>
        <p>You received this email because an account was created or an action was requested on <a href="{FRONTEND_URL}" style="color:#FF788D;">toofreshtowaste.in</a>.<br/>
        If you did not request this, you can safely ignore this email.</p>
      </div>
    </div>
  </div>
</body>
</html>"""


def _verification_email_html(name: str, verification_url: str) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for verification email."""
    subject = "Verify your email — Too Fresh To Waste"
    text_body = f"""Hi {name},

Welcome to Too Fresh To Waste! Please verify your email address by visiting:

{verification_url}

This link expires in 24 hours and can only be used once.

If you didn't create an account, you can safely ignore this email.

— The Too Fresh To Waste Team"""

    body_html = f"""
        <h2>Welcome to Too Fresh To Waste, {name}! 🎉</h2>
        <p>You're almost ready to start rescuing surplus food from amazing local cafes and bakeries near you.</p>
        <p>Please verify your email address to activate your account:</p>
        <div style="text-align:center;">
          <a href="{verification_url}" class="btn">✓ Verify My Email Address</a>
        </div>
        <p style="font-size:0.85rem; color:#94A3B8;">This link expires in <strong>24 hours</strong> and can only be used once.</p>
        <hr class="divider"/>
        <p style="font-size:0.82rem; color:#94A3B8; margin-bottom:6px;">Or copy and paste this link into your browser:</p>
        <div class="link-fallback">{verification_url}</div>
    """
    html_body = _base_email_html(subject, "Please verify your email to activate your account.", body_html)
    return subject, text_body, html_body


def _password_reset_email_html(name: str, reset_url: str) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for password reset email."""
    subject = "Reset your password — Too Fresh To Waste"
    text_body = f"""Hi {name},

We received a request to reset your password for your Too Fresh To Waste account.

Reset your password here:
{reset_url}

This link expires in 2 hours and can only be used once.

If you did not request a password reset, please ignore this email — your account is safe.

— The Too Fresh To Waste Team"""

    body_html = f"""
        <h2>Reset Your Password</h2>
        <p>Hi {name},</p>
        <p>We received a request to reset the password for your Too Fresh To Waste account.</p>
        <div style="text-align:center;">
          <a href="{reset_url}" class="btn">🔒 Reset My Password</a>
        </div>
        <p style="font-size:0.85rem; color:#94A3B8;">This link expires in <strong>2 hours</strong> and can only be used once.</p>
        <hr class="divider"/>
        <p style="font-size:0.82rem; color:#94A3B8; margin-bottom:4px;">If you didn't request a password reset, you can safely ignore this email. Your account remains secure.</p>
        <p style="font-size:0.82rem; color:#94A3B8; margin-bottom:6px;">Or copy and paste this link into your browser:</p>
        <div class="link-fallback">{reset_url}</div>
    """
    html_body = _base_email_html(subject, "You requested a password reset for your Too Fresh To Waste account.", body_html)
    return subject, text_body, html_body


# ─── Email dispatch ────────────────────────────────────────────────────────────

def _send_via_resend(to_email: str, subject: str, html: str, text: str) -> bool:
    """Send via Resend API (https://resend.com)."""
    try:
        import resend as resend_lib
        resend_lib.api_key = EMAIL_API_KEY
        resend_lib.Emails.send({
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        })
        return True
    except Exception as e:
        logger.error(f"Resend send error to {to_email}: {e}")
        return False


def _send_via_sendgrid(to_email: str, subject: str, html: str, text: str) -> bool:
    """Send via SendGrid API."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Content
        sg = sendgrid.SendGridAPIClient(api_key=EMAIL_API_KEY)
        from_email = EMAIL_FROM
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html,
        )
        sg.send(message)
        return True
    except Exception as e:
        logger.error(f"SendGrid send error to {to_email}: {e}")
        return False


def _send_via_smtp(to_email: str, subject: str, html: str, text: str) -> bool:
    """Send via Django's built-in email (SMTP / console backend in dev)."""
    try:
        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else EMAIL_FROM,
            to=[to_email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send()
        return True
    except Exception as e:
        logger.error(f"SMTP send error to {to_email}: {e}")
        return False


def _dispatch_email(to_email: str, subject: str, html: str, text: str) -> bool:
    """
    Route email to the configured provider.
    Falls back to SMTP if provider send fails.
    """
    provider = EMAIL_PROVIDER.lower()
    success = False

    if provider == 'resend' and EMAIL_API_KEY:
        success = _send_via_resend(to_email, subject, html, text)
    elif provider == 'sendgrid' and EMAIL_API_KEY:
        success = _send_via_sendgrid(to_email, subject, html, text)
    else:
        success = _send_via_smtp(to_email, subject, html, text)

    if not success and provider != 'smtp':
        logger.warning(f"Primary email provider failed. Falling back to SMTP for {to_email}.")
        success = _send_via_smtp(to_email, subject, html, text)

    return success


# ─── Public API ────────────────────────────────────────────────────────────────

def send_verification_email(user, token: str) -> bool:
    """
    Send an email verification email to the user.
    The token is appended to the frontend verify-email page URL.
    """
    verification_url = f"{FRONTEND_URL}/verify-email.html?token={token}"
    name = user.get_short_name() or user.get_full_name() or 'there'
    subject, text, html = _verification_email_html(name, verification_url)
    sent = _dispatch_email(user.email, subject, html, text)
    if sent:
        logger.info(f"Verification email sent to {user.email}")
    else:
        logger.error(f"Failed to send verification email to {user.email}")
    return sent


def send_password_reset_email(user, token: str) -> bool:
    """
    Send a password reset email to the user.
    The token is appended to the frontend reset-password page URL.
    """
    reset_url = f"{FRONTEND_URL}/reset-password.html?token={token}"
    name = user.get_short_name() or user.get_full_name() or 'there'
    subject, text, html = _password_reset_email_html(name, reset_url)
    sent = _dispatch_email(user.email, subject, html, text)
    if sent:
        logger.info(f"Password reset email sent to {user.email}")
    else:
        logger.error(f"Failed to send password reset email to {user.email}")
    return sent
