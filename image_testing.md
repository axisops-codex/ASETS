# IMAGE INTEGRATION TESTING RULES

## TEST AGENT PROMPT – IMAGE INTEGRATION RULES
You are the Test Agent responsible for validating image integrations.
Follow these rules exactly. Do not overcomplicate.

### Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — objects, edges, textures, or shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
  - Fix example: if you read a .jpg but the content is actually PNG after conversion/compression, re-detect and update the MIME after transformations.
- If the image is animated (GIF, APNG, animated WEBP), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

## App-specific: PsyBooks receipt scan
- Endpoint: POST /api/expenses/scan  body: {"image_base64": "<base64 jpeg of a receipt>"}
- Use a receipt-like JPEG containing text (merchant, date, TOTAL amount). Model: gemini-3-flash-preview via Emergent LLM key.
- Expected response JSON: { amount:number, currency, date (YYYY-MM-DD), merchant, description, category (one of the fixed list), receipt_path }
- The receipt image is stored in Emergent Object Storage; receipt_path like "psybooks/uploads/{user_id}/{uuid}.jpg".
- Serve/verify via GET /api/files/{path}?token={jwt} -> 200 image/jpeg for the owner; 401 without token; 403 for another user's path.
