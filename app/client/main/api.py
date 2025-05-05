from fastapi import HTTPException, Depends
from app.models.contact import ContactMessage, ContactMessageCreate, ContactMessageResponse
from app.database import get_db
from app.client.main.routes import router
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

# Configure logging
logger = logging.getLogger(__name__)

@router.post("/api/contact", response_model=ContactMessageResponse)
async def submit_contact_form(contact_data: ContactMessageCreate, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Submit a contact form message"""
    try:
        # Create a new contact message
        contact_message = ContactMessage(
            name=contact_data.name,
            email=contact_data.email,
            phone=contact_data.phone,
            subject=contact_data.subject,
            message=contact_data.message
        )
        
        # Save to database
        await contact_message.save()
        
        # Return success response
        return ContactMessageResponse(
            success=True,
            message="Your message has been sent successfully. We'll get back to you soon!"
        )
    except Exception as e:
        logger.error(f"Error submitting contact form: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while submitting your message. Please try again later."
        )
