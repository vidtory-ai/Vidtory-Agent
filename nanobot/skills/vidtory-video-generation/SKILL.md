---
name: vidtory-video-generation
description: Generate cinematic video clips from text prompts or reference images using Vidtory's Veo AI video generation model.
always: true
---

# Vidtory Video Generation

Use the `generate_video` tool when the user asks to create a video clip, animate an image, generate a B-roll, or create motion scenes.

## Guidelines & Best Practices

1. **Text-to-Video (t2v)**:
   - Provide a detailed visual description in the `prompt`. Include:
     - **Subject**: Who or what is the focus (e.g., "A futuristic sports car driving").
     - **Action/Motion**: Camera movement (e.g., "slow drone shot tracking the car", "dramatic low-angle pan") and subject action.
     - **Environment/Lighting**: Time of day, weather, reflections, light sources (e.g., "volumetric golden hour lighting, lens flare").
     - **Style**: Aesthetic style (e.g., "photorealistic cinematic film look, 8k resolution, color-graded").
   - Set the `aspect_ratio` based on target platform (default is `16:9` for widescreen, or `9:16` for mobile vertical video).
   - Set the `duration` in seconds (typically `4` or `8`).

2. **Image-to-Video (i2v)**:
   - If a user has generated an image or provided an image file path (from local artifacts), recommend bringing it to life with motion.
   - Pass the local image file path in the `reference_images` array parameter.
   - In the `prompt`, describe how the image should animate (e.g., "Bring the character to life: they turn their head and smile at the camera, wind gently blowing their hair, subtle camera push-in").
   - Set `mode` to `"i2v"`.

3. **Artifact Handling**:
   - The tool saves generated videos as `.mp4` artifacts and returns a JSON string containing the metadata (including the artifact `id` and the local file `path`).
   - To deliver the final video to the user, you **must** call the `message` tool and pass the local path of the video in the `media` parameter list.

## Examples

### 1. Generating a text-to-video B-roll clip:
```text
generate_video(
  prompt="A slow, cinematic tracking shot of coffee beans falling into a grinder in slow-motion, warm cozy cafe lighting, depth of field, 8k cinematic look",
  aspect_ratio="16:9",
  duration=8
)
```

### 2. Animating a previously generated image:
```text
generate_video(
  prompt="The robot head in the reference image blinks its eyes, turns slightly toward the viewer, and sparkles with subtle digital screen animations, warm background glow",
  reference_images=["/Users/brianle/.nanobot/media/generated/2026-05-24/img_8aca5aac962c.jpg"],
  aspect_ratio="1:1",
  duration=4,
  mode="i2v"
)
```
