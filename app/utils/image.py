import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, HTTPException
from config import settings
from PIL import Image
import io
import os
from datetime import datetime

def optimize_image(file: UploadFile, max_size: int = 1024, quality: int = 85):
    """
    Optimize image by resizing and compressing it
    
    Args:
        file: The uploaded file
        max_size: Maximum dimension (width or height) in pixels
        quality: JPEG/WebP compression quality (0-100)
        
    Returns:
        BytesIO object containing the optimized image
    """
    image = Image.open(file.file)
    
    # Preserve aspect ratio while resizing
    if image.width > max_size or image.height > max_size:
        if image.width > image.height:
            new_width = max_size
            new_height = int(image.height * (max_size / image.width))
        else:
            new_height = max_size
            new_width = int(image.width * (max_size / image.height))
        
        image = image.resize((new_width, new_height), Image.LANCZOS)
    
    # Convert to RGB if RGBA (remove alpha channel)
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    
    # Save to BytesIO with compression
    optimized_image = io.BytesIO()
    
    # Determine image format based on content_type or filename
    if hasattr(file, 'filename') and file.filename:
        # Get extension from filename
        _, ext = os.path.splitext(file.filename)
        ext = ext.lower().lstrip('.')
        if ext in ['jpg', 'jpeg']:
            image_format = 'JPEG'
        elif ext in ['png']:
            image_format = 'PNG'
        elif ext in ['gif']:
            image_format = 'GIF'
        elif ext in ['webp']:
            image_format = 'WEBP'
        else:
            # Default to JPEG if extension is unknown
            image_format = 'JPEG'
    elif hasattr(image, 'format') and image.format:
        image_format = image.format
    else:
        # Default to JPEG if no format info is available
        image_format = 'JPEG'
        
    # Save with chosen format
    image.save(optimized_image, format=image_format, quality=quality, optimize=True)
    optimized_image.seek(0)
    
    return optimized_image

def save_image(file: UploadFile, folder: str = settings.CLOUDINARY_BASE_FOLDER, optimize: bool = True, max_size: int = 1024, quality: int = 85):
    try:
        if optimize:
            # Reset file pointer and optimize the image
            file.file.seek(0)
            optimized_file = optimize_image(file, max_size, quality)
            
            # Upload the optimized image to Cloudinary
            result = cloudinary.uploader.upload(
                optimized_file,
                folder=folder,
                overwrite=True,
                resource_type="auto"
            )
        else:
            # Upload the original image to Cloudinary
            file.file.seek(0)
            result = cloudinary.uploader.upload(
                file.file,
                folder=folder,
                overwrite=True,
                resource_type="auto"
            )
        
        # Return the secure URL of the uploaded image
        return result['secure_url']
    except Exception as e:
        # Handle any upload errors
        print(f"Error uploading image to Cloudinary: {str(e)}")
        return None

def delete_image(image_url: str) -> bool:
    """
    Delete an image from Cloudinary using its URL
    
    Args:
        image_url: The URL of the image to delete
        
    Returns:
        bool: True if image was deleted successfully, False otherwise
    """
    try:
        # Extract the public ID from the Cloudinary URL
        # Format: https://res.cloudinary.com/cloud_name/image/upload/v1234567890/folder/public_id.ext
        # We need the part after the last slash, without the extension
        if not image_url:
            return False
            
        # Get the filename from the URL (after the last slash)
        filename = image_url.split('/')[-1]
        
        # Remove the extension to get the public ID
        public_id = os.path.splitext(filename)[0]
        
        # For images in folders, include the folder in the public ID
        if settings.CLOUDINARY_BASE_FOLDER:
            folder_part = image_url.split('/upload/')[1].split(filename)[0].strip('/')
            if folder_part:
                public_id = f"{folder_part}/{public_id}"
        
        # Delete the image from Cloudinary
        result = cloudinary.uploader.destroy(public_id)
        
        # Return True if the image was deleted successfully
        return result.get('result') == 'ok'
    except Exception as e:
        # Log any errors for debugging
        print(f"Error deleting image from Cloudinary: {str(e)}")
        return False

def delete_images(image_urls: list) -> dict:
    """
    Delete multiple images from Cloudinary
    
    Args:
        image_urls: List of image URLs to delete
        
    Returns:
        dict: Dictionary with success count and failed count
    """
    if not image_urls:
        return {"success": 0, "failed": 0}
        
    success_count = 0
    failed_count = 0
    
    for url in image_urls:
        if delete_image(url):
            success_count += 1
        else:
            failed_count += 1
    
    return {
        "success": success_count,
        "failed": failed_count
    }

async def validate_and_optimize_product_image(file: UploadFile, max_size_mb: int = 5, max_dimension: int = 2000):
    """
    Validates and optimizes a product image, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB
        max_dimension: Maximum image dimension in pixels
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Use the existing save_image function to optimize and upload
        cloudinary_url = save_image(
            file=UploadFile(filename=file.filename, file=file_obj),
            folder="products",
            optimize=True,
            max_size=min(max_dimension, 2000),  # Cap at 2000px
            quality=quality
        )
        
        if not cloudinary_url:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload image to Cloudinary"
            )
            
        return cloudinary_url
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing product image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )

async def validate_and_optimize_banner_image(file: UploadFile, max_size_mb: int = 5, max_dimension: int = 2000):
    """
    Validates and optimizes a banner image, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB
        max_dimension: Maximum image dimension in pixels
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Use the existing save_image function to optimize and upload
        cloudinary_url = save_image(
            file=UploadFile(filename=file.filename, file=file_obj),
            folder="banners",
            optimize=True,
            max_size=min(max_dimension, 2000),  # Cap at 2000px
            quality=quality
        )
        
        if not cloudinary_url:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload image to Cloudinary"
            )
            
        return cloudinary_url
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing banner image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )

async def save_icon(file: UploadFile, max_size_mb: int = 2, max_dimension: int = 64):
    """
    Validates and optimizes a category icon, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB (default: 2MB)
        max_dimension: Maximum image dimension in pixels (default: 64px)
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Generate a unique filename for Cloudinary
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"category_icon_{timestamp}{file_extension}"
        
        # Upload directly to Cloudinary with the correct folder structure
        result = cloudinary.uploader.upload(
            file_obj,
            folder=f"{settings.CLOUDINARY_BASE_FOLDER}/categories",
            public_id=unique_filename,
            overwrite=True,
            resource_type="auto",
            transformation=[
                {"width": max_dimension, "height": max_dimension, "crop": "fill"},
                {"quality": quality}
            ]
        )
        
        if not result or 'secure_url' not in result:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload icon to Cloudinary"
            )
            
        return result['secure_url']
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing category icon: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing icon: {str(e)}"
        )

async def validate_and_optimize_collection_image(file: UploadFile, max_size_mb: int = 5, max_dimension: int = 2000):
    """
    Validates and optimizes a collection image, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB
        max_dimension: Maximum image dimension in pixels
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Use the existing save_image function to optimize and upload
        cloudinary_url = save_image(
            file=UploadFile(filename=file.filename, file=file_obj),
            folder="collections",
            optimize=True,
            max_size=min(max_dimension, 2000),  # Cap at 2000px
            quality=quality
        )
        
        if not cloudinary_url:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload image to Cloudinary"
            )
            
        return cloudinary_url
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing collection image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )

async def validate_and_optimize_brand_image(file: UploadFile, max_size_mb: int = 2, max_dimension: int = 200):
    """
    Validates and optimizes a brand image, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB (default: 2MB)
        max_dimension: Maximum image dimension in pixels (default: 200px)
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Generate a unique filename for Cloudinary
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"brand_icon_{timestamp}{file_extension}"
        
        # Upload directly to Cloudinary with the correct folder structure
        result = cloudinary.uploader.upload(
            file_obj,
            folder=f"{settings.CLOUDINARY_BASE_FOLDER}/brands",
            public_id=unique_filename,
            overwrite=True,
            resource_type="auto",
            transformation=[
                {"width": max_dimension, "height": max_dimension, "crop": "fill"},
                {"quality": quality}
            ]
        )
        
        if not result or 'secure_url' not in result:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload brand image to Cloudinary"
            )
            
        return result['secure_url']
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing brand image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )

async def validate_and_optimize_scent_image(file: UploadFile, max_size_mb: int = 5, max_dimension: int = 2000):
    """
    Validates and optimizes a scent image, then uploads to Cloudinary
    
    Args:
        file: The uploaded image file
        max_size_mb: Maximum file size in MB
        max_dimension: Maximum image dimension in pixels
        
    Returns:
        Cloudinary secure URL for the uploaded image
        
    Raises:
        HTTPException: If validation fails or upload fails
    """
    try:
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Missing filename"
            )
            
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if not file_extension:
            raise HTTPException(
                status_code=400,
                detail="Could not determine file extension"
            )
        
        if file_extension not in valid_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed extensions are: {', '.join(valid_extensions)}"
            )
        
        # Check if content-type is image
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is not an image"
            )
        
        # Read file into memory to check size
        file.file.seek(0)
        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        
        # If image is too large, optimize it more aggressively
        quality = 85
        if size_mb > max_size_mb:
            quality = 65  # Lower quality for large files
            
        # Create a BytesIO object with the contents
        file_obj = io.BytesIO(contents)
        
        # Use the existing save_image function to optimize and upload
        cloudinary_url = save_image(
            file=UploadFile(filename=file.filename, file=file_obj),
            folder="scents",
            optimize=True,
            max_size=min(max_dimension, 2000),  # Cap at 2000px
            quality=quality
        )
        
        if not cloudinary_url:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload image to Cloudinary"
            )
            
        return cloudinary_url
        
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        # Handle any other errors
        print(f"Error processing scent image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )
