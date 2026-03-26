"""Image generation using FAL.ai models (SDXL, FLUX) and Google Gemini (Imagen)."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve

import fal_client

from . import db


class ImageGenerationError(Exception):
    """Error generating image."""


# Available models for configuration
AVAILABLE_MODELS = {
    "sdxl": "fal-ai/fast-sdxl",
    "sdxl-lightning": "fal-ai/fast-lightning-sdxl",
    "flux-schnell": "fal-ai/flux/schnell",
    "flux-dev": "fal-ai/flux/dev",
    "flux-pro": "fal-ai/flux-pro",
    "nano-banana-2": "fal-ai/nano-banana-2",
}

GEMINI_MODELS = {
    "imagen-3": "imagen-3.0-generate-002",
    "gemini-2.5-flash-image": "gemini-2.5-flash-image",
    "gemini-3-pro": "gemini-3-pro-image-preview",
}

# Supported aspect ratios for Gemini native image generation
GEMINI_ASPECT_RATIOS = [
    (1, 1),    # 1:1
    (2, 3),    # 2:3
    (3, 2),    # 3:2
    (3, 4),    # 3:4
    (4, 3),    # 4:3
    (4, 5),    # 4:5
    (5, 4),    # 5:4
    (9, 16),   # 9:16
    (16, 9),   # 16:9
    (21, 9),   # 21:9
]


def get_closest_gemini_aspect_ratio(width: int, height: int) -> str:
    """Find the closest supported Gemini aspect ratio for given dimensions.

    Args:
        width: Target width
        height: Target height

    Returns:
        Aspect ratio string like "16:9" or "21:9"
    """
    target_ratio = width / height
    closest = min(GEMINI_ASPECT_RATIOS, key=lambda r: abs(r[0] / r[1] - target_ratio))
    return f"{closest[0]}:{closest[1]}"

def get_resolution_for_size(width: int, height: int) -> str:
    """Map target dimensions to a Nano Banana 2 resolution tier."""
    max_dim = max(width, height)
    if max_dim <= 512:
        return "0.5K"
    elif max_dim <= 1024:
        return "1K"
    elif max_dim <= 2048:
        return "2K"
    else:
        return "4K"


# Negative prompts to exclude conflicting styles
STYLE_NEGATIVE_PROMPTS = {
    "Realistic": "cartoon, anime, illustration, painting, drawn, sketch, artificial",
    "Digital Painting": "photograph, photo, realistic, photorealistic, raw photo",
    "Anime": "photograph, photo, realistic, photorealistic, western, 3d render",
    "Oil Painting": "photograph, photo, digital, anime, cartoon, 3d render",
    "Minimalist": "busy, cluttered, detailed, complex, ornate, photograph",
    "Photographic": "cartoon, anime, illustration, painting, drawn, digital art",
}


def get_fal_key() -> str:
    """Get the FAL API key from environment."""
    key = os.environ.get("FAL_KEY")
    if not key:
        raise ImageGenerationError(
            "FAL_KEY environment variable not set. "
            "Get your key at https://fal.ai/dashboard/keys"
        )
    return key


def get_gemini_key() -> str:
    """Get the Gemini API key from environment."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ImageGenerationError(
            "GEMINI_API_KEY environment variable not set. "
            "Get your key at https://aistudio.google.com/apikey"
        )
    return key


def get_negative_prompt(style: str) -> str:
    """Get the negative prompt for a style to exclude conflicting styles."""
    base_negative = "text, watermark, signature, logo, UI elements, blurry, low quality"
    style_negative = STYLE_NEGATIVE_PROMPTS.get(style, "")
    if style_negative:
        return f"{base_negative}, {style_negative}"
    return base_negative


def upscale_image(image_url: str, scale: int = 2) -> str:
    """Upscale an image using ESRGAN.

    Args:
        image_url: URL of the image to upscale
        scale: Upscale factor (2 or 4)

    Returns:
        URL of the upscaled image
    """
    model_name = "RealESRGAN_x2plus" if scale == 2 else "RealESRGAN_x4plus"

    print(f"DEBUG: Upscaling {scale}x with {model_name}")

    result = fal_client.subscribe(
        "fal-ai/esrgan",
        arguments={
            "image_url": image_url,
            "model": model_name,
        },
    )

    if not result or "image" not in result:
        raise ImageGenerationError("Failed to upscale image")

    return result["image"]["url"]


def calculate_generation_size(target_width: int, target_height: int) -> tuple[int, int, int]:
    """Calculate optimal generation size for extreme aspect ratios.

    SDXL works best around 1 megapixel. For extreme aspect ratios,
    we generate smaller and upscale.

    Args:
        target_width: Desired final width
        target_height: Desired final height

    Returns:
        Tuple of (gen_width, gen_height, upscale_factor)
    """
    aspect_ratio = target_width / target_height

    # Standard 16:9 or narrower - generate directly
    if aspect_ratio <= 2.0:
        return target_width, target_height, 1

    # Ultrawide (32:9 etc) - generate at half size and upscale 2x
    if aspect_ratio <= 4.0:
        return target_width // 2, target_height // 2, 2

    # Super ultrawide - generate at quarter size and upscale 4x
    return target_width // 4, target_height // 4, 4


def generate_image_gemini(
    prompt: str,
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    model: str = "imagen-3.0-generate-002",
    width: int = 1920,
    height: int = 1080,
) -> tuple[str, int]:
    """Generate an image using Google Gemini (Imagen or Gemini native).

    Args:
        prompt: The full prompt for image generation
        category: Category for filename
        style: Style for filename
        mood: Mood used (for reference)
        custom_input: Custom user input (for reference)
        model: Gemini model to use
        width: Image width
        height: Image height

    Returns:
        Tuple of (image_path, generation_id)
    """
    from google import genai
    from google.genai import types

    # Ensure Gemini key is available
    api_key = get_gemini_key()
    client = genai.Client(api_key=api_key)

    print(f"DEBUG: Generating with Gemini model: {model}")

    # Determine if this is an Imagen model or Gemini native model
    is_imagen = model.startswith("imagen")

    # Prepare to save image
    images_dir = db.get_images_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_category = category.lower().replace(" ", "-").replace("/", "-")
    safe_style = style.lower().replace(" ", "-").replace("/", "-")
    filename = f"{timestamp}_{safe_category}_{safe_style}.png"
    image_path = images_dir / filename

    if is_imagen:
        # Use Imagen API (generate_images)
        aspect_ratio = f"{width}:{height}"
        print(f"DEBUG: Using Imagen API with aspect ratio: {aspect_ratio}")

        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
                output_mime_type="image/png",
            ),
        )

        if not response.generated_images:
            raise ImageGenerationError("No image returned from Gemini Imagen API")

        # Save from Imagen response
        response.generated_images[0].image.save(image_path)
    else:
        # Use Gemini native image generation (generate_content)
        aspect_ratio = get_closest_gemini_aspect_ratio(width, height)
        print(f"DEBUG: Using Gemini native image generation API with aspect ratio: {aspect_ratio}, size: 2K")

        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size="2K",
                ),
            ),
        )

        # Extract image from response
        image_data = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_data = part.inline_data.data
                    break

        if not image_data:
            raise ImageGenerationError("No image returned from Gemini API")

        # Save image data to file
        with open(image_path, "wb") as f:
            f.write(image_data)

    # Save to database
    generation_id = db.save_generation(
        prompt=prompt,
        image_path=str(image_path),
        category=category,
        style=style,
        mood=mood,
        custom_input=custom_input,
    )

    return str(image_path), generation_id


def generate_image(
    prompt: str,
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    model: str = "fal-ai/fast-sdxl",
    width: int = 1920,
    height: int = 1080,
    provider: str = "fal",
) -> tuple[str, int]:
    """Generate an image using FAL.ai or Gemini.

    Args:
        prompt: The full prompt for image generation
        category: Category for filename
        style: Style for filename
        mood: Mood used (for reference)
        custom_input: Custom user input (for reference)
        model: Model to use (provider-specific)
        width: Image width
        height: Image height
        provider: Image generation provider ("fal" or "gemini")

    Returns:
        Tuple of (image_path, generation_id)
    """
    # Dispatch to provider-specific implementation
    if provider == "gemini":
        return generate_image_gemini(
            prompt, category, style, mood, custom_input, model, width, height
        )

    # FAL.ai implementation follows
    # Ensure FAL key is available
    get_fal_key()

    # Build arguments based on model type
    is_nano_banana = "nano-banana" in model

    if is_nano_banana:
        # Nano Banana 2 uses aspect_ratio and resolution instead of image_size
        resolution = get_resolution_for_size(width, height)
        arguments = {
            "prompt": prompt,
            "num_images": 1,
            "aspect_ratio": "auto",
            "resolution": resolution,
        }
        upscale_factor = 1
        gen_width, gen_height = width, height
        print(f"DEBUG: Nano Banana 2 with aspect_ratio=auto, resolution={resolution}")
    else:
        # Calculate optimal generation size (may need upscaling for ultrawide)
        gen_width, gen_height, upscale_factor = calculate_generation_size(width, height)

        arguments = {
            "prompt": prompt,
            "image_size": {
                "width": gen_width,
                "height": gen_height,
            },
            "num_images": 1,
        }

        # Add SDXL-specific parameters
        if "sdxl" in model:
            arguments["negative_prompt"] = get_negative_prompt(style)
            arguments["guidance_scale"] = 9.0  # Higher for better prompt adherence
            arguments["num_inference_steps"] = 30
        else:
            arguments["enable_safety_checker"] = True

    # Debug: print what we're sending
    print(f"DEBUG: Target size: {width}x{height}, generating at: {gen_width}x{gen_height}, upscale: {upscale_factor}x")
    print(f"DEBUG: Sending to model: {model}")

    # Generate the image
    result = fal_client.subscribe(
        model,
        arguments=arguments,
    )

    if not result or "images" not in result or not result["images"]:
        raise ImageGenerationError("No image returned from FAL API")

    image_url = result["images"][0]["url"]

    # Upscale if needed
    if upscale_factor > 1:
        image_url = upscale_image(image_url, upscale_factor)

    # Download and save the image
    images_dir = db.get_images_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize category and style for filename
    safe_category = category.lower().replace(" ", "-").replace("/", "-")
    safe_style = style.lower().replace(" ", "-").replace("/", "-")
    filename = f"{timestamp}_{safe_category}_{safe_style}.png"
    image_path = images_dir / filename

    urlretrieve(image_url, image_path)

    # Save to database
    generation_id = db.save_generation(
        prompt=prompt,
        image_path=str(image_path),
        category=category,
        style=style,
        mood=mood,
        custom_input=custom_input,
    )

    return str(image_path), generation_id


async def generate_image_gemini_async(
    prompt: str,
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    model: str = "imagen-3.0-generate-002",
    width: int = 1920,
    height: int = 1080,
) -> tuple[str, int]:
    """Async version of generate_image_gemini using Google Gemini (Imagen).

    Args:
        prompt: The full prompt for image generation
        category: Category for filename
        style: Style for filename
        mood: Mood used (for reference)
        custom_input: Custom user input (for reference)
        model: Gemini model to use
        width: Image width
        height: Image height

    Returns:
        Tuple of (image_path, generation_id)
    """
    import asyncio

    # Run sync Gemini call in executor (google-genai doesn't have native async)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: generate_image_gemini(
            prompt, category, style, mood, custom_input, model, width, height
        ),
    )


async def generate_image_async(
    prompt: str,
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    model: str = "fal-ai/fast-sdxl",
    width: int = 1920,
    height: int = 1080,
    provider: str = "fal",
) -> tuple[str, int]:
    """Async version of generate_image using FAL.ai or Gemini.

    Args:
        prompt: The full prompt for image generation
        category: Category for filename
        style: Style for filename
        mood: Mood used (for reference)
        custom_input: Custom user input (for reference)
        model: Model to use (provider-specific)
        width: Image width
        height: Image height
        provider: Image generation provider ("fal" or "gemini")

    Returns:
        Tuple of (image_path, generation_id)
    """
    # Dispatch to provider-specific implementation
    if provider == "gemini":
        return await generate_image_gemini_async(
            prompt, category, style, mood, custom_input, model, width, height
        )

    import aiohttp

    # FAL.ai implementation follows
    # Ensure FAL key is available
    get_fal_key()

    # Build arguments based on model type
    is_nano_banana = "nano-banana" in model

    if is_nano_banana:
        resolution = get_resolution_for_size(width, height)
        arguments = {
            "prompt": prompt,
            "num_images": 1,
            "aspect_ratio": "auto",
            "resolution": resolution,
        }
    else:
        # Calculate optimal generation size (may need upscaling for ultrawide)
        gen_width, gen_height, upscale_factor = calculate_generation_size(width, height)

        arguments = {
            "prompt": prompt,
            "image_size": {
                "width": gen_width,
                "height": gen_height,
            },
            "num_images": 1,
        }

        # Add SDXL-specific parameters
        if "sdxl" in model:
            arguments["negative_prompt"] = get_negative_prompt(style)
            arguments["guidance_scale"] = 9.0
            arguments["num_inference_steps"] = 30
        else:
            arguments["enable_safety_checker"] = True

    # Generate the image
    handler = await fal_client.submit_async(
        model,
        arguments=arguments,
    )

    result = await handler.get()

    if not result or "images" not in result or not result["images"]:
        raise ImageGenerationError("No image returned from FAL API")

    image_url = result["images"][0]["url"]

    # Upscale if needed (sync call within async - could be improved)
    if not is_nano_banana and upscale_factor > 1:
        image_url = upscale_image(image_url, upscale_factor)

    # Download and save the image
    images_dir = db.get_images_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_category = category.lower().replace(" ", "-").replace("/", "-")
    safe_style = style.lower().replace(" ", "-").replace("/", "-")
    filename = f"{timestamp}_{safe_category}_{safe_style}.png"
    image_path = images_dir / filename

    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status == 200:
                with open(image_path, "wb") as f:
                    f.write(await response.read())
            else:
                raise ImageGenerationError(f"Failed to download image: HTTP {response.status}")

    # Save to database
    generation_id = db.save_generation(
        prompt=prompt,
        image_path=str(image_path),
        category=category,
        style=style,
        mood=mood,
        custom_input=custom_input,
    )

    return str(image_path), generation_id


def get_model_id(model_name: str) -> str:
    """Get the FAL model ID from a friendly name."""
    return AVAILABLE_MODELS.get(model_name, model_name)
