from fastapi_mail import FastMail, MessageSchema
from pydantic import EmailStr
from typing import List
from config import settings

async def send_email(subject: str, recipients: List[EmailStr], body: str, html_body: str = None):
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=html_body if html_body else body,
        subtype="html"
    )
    
    fm = FastMail(settings.mail_config)
    await fm.send_message(message)
