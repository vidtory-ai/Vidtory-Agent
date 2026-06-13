---
name: vidtory-audio-generation
description: Convert text scripts into high-quality spoken audio voiceovers (TTS) using Vidtory's AI voice models.
always: true
---

# Vidtory Audio Generation (TTS)

Use the `generate_audio` tool when the user wants to generate speech, voiceover, narrative script reading, or character voices from a text prompt.

## Guidelines & Best Practices

1. **Script Composition**:
   - Write clear, natural scripts. Include punctuation (commas, periods, question marks) to give the model natural pausing cues.
   - For Vietnamese scripts, use proper accentuation and spelling.
   - For complex names or numbers, write them out phonetically if the model struggles with pronunciation (e.g. "Vidtory" can be written or left as-is, but acronyms like "AI" should be spelled out or left based on voice characteristics).

2. **Selecting the Voice ID**:
   - By default, the tool uses Vidtory's premium voices.
   - **Default Voice** (Voice ID: `eZ248pfac00g3092s7h8`): A warm, professional, friendly, calm, and trustworthy voice ideal for advertisements, tutorials, and narrations.
   - Users can pass custom ElevenLabs voice IDs if needed.

3. **Speed & Language Controls**:
   - Use `speed` to control the rate of speech (default is `1.0`. Set to `0.85` for a slower, more deliberate pacing, or `1.15` for faster delivery).
   - Use `language_code` to specify the language format (default is `vi` for Vietnamese, or `en` for English).

4. **Artifact Delivery**:
   - The tool returns metadata containing the saved audio file path (typically under a `.mp3` extension).
   - Use the `message` tool with the audio file path in the `media` parameter list to deliver the voiceover directly to the user.

## Examples

### 1. Generating a Vietnamese narration with the default voice:
```text
generate_audio(
  prompt="Chào mừng bạn đến với giải pháp thiết kế video trí tuệ nhân tạo của Vidtory. Hãy để chúng tôi chắp cánh cho ý tưởng của bạn.",
  voice_id="eZ248pfac00g3092s7h8",
  language_code="vi"
)
```

### 2. Generating a slightly slower English announcement:
```text
generate_audio(
  prompt="Welcome to Vidtory Agent. Ready to create your next cinematic masterpiece.",
  language_code="en",
  speed=0.9
)
```
