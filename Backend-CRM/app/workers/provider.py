from typing import Optional
from uuid import uuid4
from app.models import MessageChannel


class MockProvider:
    """Mock provider for SMS, WhatsApp, and Email channels."""
    
    def send(
        self,
        channel: MessageChannel,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        from_email: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Mock send method. Prints data and returns a fake provider_message_id.
        
        Args:
            channel: MessageChannel enum (sms, whatsapp, email)
            to: Recipient phone/email
            body: Message body
            from_number: Sender phone (for SMS/WhatsApp)
            from_email: Sender email (for Email)
            metadata: Additional metadata
            
        Returns:
            provider_message_id: UUID string
        """
        provider_message_id = str(uuid4())
        
        print(f"[MOCK PROVIDER] Sending {channel.value} message")
        print(f"  To: {to}")
        print(f"  From: {from_number or from_email or 'N/A'}")
        print(f"  Body: {body[:100]}...")
        print(f"  Provider Message ID: {provider_message_id}")
        if metadata:
            print(f"  Metadata: {metadata}")
        
        return provider_message_id


# Placeholder classes for real providers (not implemented)
class TwilioProvider:
    """Placeholder for Twilio SMS provider."""
    pass


class WhatsAppCloudProvider:
    """Placeholder for WhatsApp Cloud API provider."""
    pass


class SendGridProvider:
    """Placeholder for SendGrid Email provider."""
    pass

