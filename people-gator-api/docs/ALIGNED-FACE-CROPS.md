# Aligned face crops

`GET /api/v1/faces/{detection_id}/aligned_crop` requires browse authentication
and returns a JPEG aligned to the five-point ArcFace template. It preserves
the source's pixel scale and optionally downscales to `max_width`; it never
upscales to that width. Successful responses retain `X-Cache: HIT` / `MISS`
and content-addressed cache keys, including the stored landmark coordinates.

Stored faces whose landmarks cannot produce a usable alignment return HTTP
**422** with this existing structured media-error shape:

```json
{
  "detail": {
    "code": "invalid_face_keypoints",
    "message": "face keypoints cannot produce a usable alignment"
  }
}
```

Finite coordinates alone do not ensure usable geometry. Coincident points,
zero source variance (including floating-point underflow), failed numerical
decomposition, non-finite calculations and non-positive scales are rejected.
There is no absolute landmark-distance tolerance: small or rotated faces remain
valid when their calculations are representable. Before allocating an image,
the native canvas must have positive finite dimensions, at most 65,500 pixels
per side and at most 89,478,485 pixels in total (Pillow's default source-image
warning threshold). `max_width` is applied after native alignment and cannot
make an unusable native canvas valid.

The request neither changes stored detections, assignments or processing times,
nor writes a failed crop to the cache. Clients can handle this isolated media
failure with their existing unavailable-image state. No fallback geometry is
invented. Image decoding and storage errors keep their existing handling.

Missing landmark types retain `insufficient_keypoints`, source mismatches retain
`source_mismatch`, and widths above the configured request limit retain
`invalid_max_width` (all HTTP 422). Non-positive widths retain HTTP request
validation. No migration or request/success-payload schema change is required.

See the [synthetic preview scenario](PREVIEW-SEEDING.md#unalignable-stored-face-64)
for a repeatable local example alongside a valid control.
