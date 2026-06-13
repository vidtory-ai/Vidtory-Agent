---
name: vidtory-creative-workflow
description: Design and execute complete multi-modal creative workflows combining scriptwriting, image design, animation (i2v), and voiceovers.
always: true
---

# Vidtory Creative Workflows

Use the guidelines in this skill when a user wants to create a complete marketing clip, advertising campaign, video story, or multi-modal project.

## Multi-Modal Workflow Pipeline

To create a full video project with narration, follow this step-by-step workflow:

1. **Step 1: Planning and Scripting**
   - Converse with the user to outline the project's goals, tone, visual style, and target duration.
   - Write a script for the audio voiceover.
   - Design visual prompts that describe key scenes matching the script.

2. **Step 2: Generate Visual B-Roll (Text-to-Image / Image-to-Video)**
   - Generate a high-quality keyframe image using `generate_image` based on the visual design.
   - Take the generated image artifact path (`img_xxxxxx.jpg`) and pass it to `generate_video` under the `reference_images` parameter.
   - Describe the animation in the video prompt (Image-to-Video mode) to produce a dynamic cinematic video.

3. **Step 3: Generate Voiceover Narration**
   - Use `generate_audio` to synthesize the spoken voiceover based on the script written in Step 1.
   - By default, use Vidtory's warm voice (Voice ID: `eZ248pfac00g3092s7h8`).

4. **Step 4: Deliver and Present**
   - Call the `message` tool with both the video and audio artifact paths in the `media` parameter list.
   - Present a professional production summary to the user outlining the assets created, the prompt choices, and how they match the original creative vision.

## Case Study: Cyberpunk Cafe Promo

- **Objective**: Create a short promo for a cozy cyberpunk-themed cafe.
- **Workflow Execution**:
  1. Call `generate_image(prompt="A cozy cafe inside a cyberpunk neon-lit street, rain sliding down the glass windows, warm amber light glowing from the interior, cinematic, 16:9", aspect_ratio="16:9")`.
  2. Extract path (e.g. `/path/to/img_123.jpg`).
  3. Call `generate_video(prompt="The rain sliding down the window pane speeds up, coffee steam gently rises from a mug on the counter, subtle camera push-in toward the interior", reference_images=["/path/to/img_123.jpg"], mode="i2v", aspect_ratio="16:9")`.
  4. Call `generate_audio(prompt="Hãy trốn cơn mưa tầm tã bên ngoài, tìm kiếm sự bình yên và ấm áp tại quán cà phê Cyberpunk của chúng tôi.", voice_id="eZ248pfac00g3092s7h8")`.
  5. Use `message(..., media=["/path/to/vid_456.mp4", "/path/to/aud_789.mp3"])` to deliver the final products.
