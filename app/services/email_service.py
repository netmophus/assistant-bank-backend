"""
Service d'envoi d'emails via Gmail SMTP.
"""
import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM_NAME", "Miznas Pilot")


def _send_sync(to_email: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SMTP_FROM} <{SMTP_USER}>"
    msg["To"]      = to_email

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())


async def send_email(to_email: str, subject: str, html_body: str) -> None:
    """Envoie un email de manière asynchrone (thread executor)."""
    await asyncio.to_thread(_send_sync, to_email, subject, html_body)


def reset_password_html(reset_link: str, user_name: str = "") -> str:
    name_line = f"<p style='color:#CBD5E1;font-size:15px;'>Bonjour <strong>{user_name}</strong>,</p>" if user_name else ""
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0A1434;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0A1434;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#0F1E48;border-radius:20px;border:1px solid rgba(201,168,76,0.25);overflow:hidden;max-width:560px;">

        <!-- Header -->
        <tr>
          <td style="background:#070E28;padding:28px 36px;border-bottom:2px solid #C9A84C;">
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#1B3A8C;border-radius:10px;width:42px;height:42px;text-align:center;vertical-align:middle;">
                  <span style="color:#C9A84C;font-size:20px;font-weight:900;">M</span>
                </td>
                <td style="padding-left:12px;">
                  <p style="margin:0;color:#FFFFFF;font-size:18px;font-weight:900;letter-spacing:1px;">MIZNAS PILOT</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 36px 28px;">
            {name_line}
            <p style="color:#CBD5E1;font-size:15px;line-height:1.6;margin:0 0 16px;">
              Vous avez demandé la réinitialisation de votre mot de passe.<br>
              Cliquez sur le bouton ci-dessous pour créer un nouveau mot de passe.
            </p>
            <p style="color:rgba(203,213,225,0.55);font-size:13px;margin:0 0 28px;">
              Ce lien est valable pendant <strong style="color:#C9A84C;">1 heure</strong>.
            </p>

            <!-- CTA -->
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#C9A84C;border-radius:12px;">
                  <a href="{reset_link}" style="display:inline-block;padding:14px 32px;color:#0A1434;font-size:15px;font-weight:700;text-decoration:none;letter-spacing:0.3px;">
                    Réinitialiser mon mot de passe →
                  </a>
                </td>
              </tr>
            </table>

            <p style="color:rgba(203,213,225,0.4);font-size:12px;margin:24px 0 0;line-height:1.6;">
              Si vous n'avez pas fait cette demande, ignorez cet email.<br>
              Votre mot de passe restera inchangé.
            </p>

            <!-- Lien texte de secours -->
            <p style="color:rgba(203,213,225,0.3);font-size:11px;margin:16px 0 0;">
              Lien de secours :<br>
              <a href="{reset_link}" style="color:#C9A84C;word-break:break-all;">{reset_link}</a>
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#070E28;padding:18px 36px;border-top:1px solid rgba(27,58,140,0.3);">
            <p style="margin:0;color:rgba(203,213,225,0.3);font-size:11px;text-align:center;">
              Miznas Pilot &copy; 2025 · Plateforme bancaire UEMOA · www.miznas-pilot.io
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""
