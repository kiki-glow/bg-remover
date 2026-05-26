from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove, new_session
from PIL import Image, ImageFilter
import numpy as np
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session = new_session("isnet-general-use")


def is_solid_background(image: Image.Image, threshold: int = 30) -> tuple[bool, tuple]:
    img = image.convert("RGB")
    w, h = img.size
    corners = [
        img.getpixel((0, 0)), img.getpixel((w-1, 0)),
        img.getpixel((0, h-1)), img.getpixel((w-1, h-1)),
        img.getpixel((w//2, 0)), img.getpixel((0, h//2)),
        img.getpixel((w-1, h//2)), img.getpixel((w//2, h-1)),
    ]
    r_vals = [c[0] for c in corners]
    g_vals = [c[1] for c in corners]
    b_vals = [c[2] for c in corners]
    if (max(r_vals) - min(r_vals) < threshold and
        max(g_vals) - min(g_vals) < threshold and
        max(b_vals) - min(b_vals) < threshold):
        avg = (int(sum(r_vals)/len(r_vals)),
               int(sum(g_vals)/len(g_vals)),
               int(sum(b_vals)/len(b_vals)))
        return True, avg
    return False, (255, 255, 255)


def remove_solid_color_bg(image: Image.Image, bg_color: tuple, tolerance: int = 35) -> Image.Image:
    img = image.convert("RGBA")
    data = np.array(img, dtype=np.float32)
    br, bg_c, bb = bg_color

    color_mask = (
        (np.abs(data[:, :, 0] - br) < tolerance) &
        (np.abs(data[:, :, 1] - bg_c) < tolerance) &
        (np.abs(data[:, :, 2] - bb) < tolerance)
    )

    # Pass 1: flood-fill from all edges to remove outer background
    h, w = color_mask.shape
    visited = np.zeros((h, w), dtype=bool)
    stack = []
    for corner in [(0, 0), (0, w-1), (h-1, 0), (h-1, w-1)]:
        if color_mask[corner]:
            stack.append(corner)
    # Also seed from all border pixels
    for x in range(w):
        if color_mask[0, x]: stack.append((0, x))
        if color_mask[h-1, x]: stack.append((h-1, x))
    for y in range(h):
        if color_mask[y, 0]: stack.append((y, 0))
        if color_mask[y, w-1]: stack.append((y, w-1))

    while stack:
        cy, cx = stack.pop()
        if cy < 0 or cy >= h or cx < 0 or cx >= w:
            continue
        if visited[cy, cx] or not color_mask[cy, cx]:
            continue
        visited[cy, cx] = True
        stack.extend([(cy+1, cx), (cy-1, cx), (cy, cx+1), (cy, cx-1)])

    result = data.copy()
    result[visited, 3] = 0

    # Pass 2: remove bg-colored pixels that are completely surrounded by
    # already-transparent pixels (catches enclosed dots/specks on circuit traces)
    alpha = result[:, :, 3]
    transparent = (alpha == 0)

    # Dilate the transparent region by a few pixels to create a "near-transparent" mask
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(transparent, iterations=6)

    # Any pixel that: matches bg color AND is within the dilated transparent zone
    # is a stray speck left behind — remove it
    speck_mask = color_mask & dilated & ~visited
    result[speck_mask, 3] = 0

    # Smooth alpha edges
    alpha_img = Image.fromarray(result[:, :, 3].astype(np.uint8))
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=0.5))
    result[:, :, 3] = np.array(alpha_img)

    return Image.fromarray(result.astype(np.uint8), "RGBA")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/remove-bg")
async def remove_bg(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    original_size = image.size

    solid, bg_color = is_solid_background(image)

    if solid:
        output = remove_solid_color_bg(image, bg_color)
    else:
        MAX_DIM = 1024
        process_img = image.copy()
        max_dim = max(process_img.size)
        if max_dim > MAX_DIM:
            scale = MAX_DIM / max_dim
            new_size = (int(process_img.size[0] * scale), int(process_img.size[1] * scale))
            process_img = process_img.resize(new_size, Image.LANCZOS)

        output = remove(process_img, session=session, alpha_matting=False, post_process_mask=True)

        if output.size != original_size:
            output = output.resize(original_size, Image.LANCZOS)

        r, g, b, a = output.split()
        a = a.filter(ImageFilter.GaussianBlur(radius=0.8))
        output = Image.merge("RGBA", (r, g, b, a))

    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")
