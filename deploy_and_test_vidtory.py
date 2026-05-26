import asyncio
import json
import os
import sys
from pathlib import Path

# Setup sys.path to import local nanobot package
sys.path.insert(0, str(Path(__file__).parent))

from nanobot.providers.image_generation import VidtoryImageGenerationClient
from nanobot.providers.video_generation import VidtoryVideoGenerationClient
from nanobot.providers.audio_generation import VidtoryAudioGenerationClient

from nanobot.agent.tools.image_generation import ImageGenerationTool, ImageGenerationToolConfig
from nanobot.agent.tools.video_generation import VideoGenerationTool, VideoGenerationToolConfig
from nanobot.agent.tools.audio_generation import AudioGenerationTool, AudioGenerationToolConfig
from nanobot.config.schema import ProviderConfig

API_KEY = "vidtory_a47b8b3f172e354ef51fbb741a8ed4e29206417d8c506a50d64323227b7b96c7"
WORKSPACE = Path(__file__).parent.resolve()

async def test_llm_system():
    print("\n--- 1. Testing Vidtory LLM System (Text Generation) ---")
    import httpx
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    url = "https://bapi.vidtory.net/generative-core/text"
    
    prompt = (
        "Generate a highly detailed, short prompt (1 sentence) for creating "
        "a cinematic image of a futuristic neon city in rain."
    )
    
    body = {
        "prompt": prompt,
        "modelId": "gemini-3-flash-preview"
    }
    
    async with httpx.AsyncClient() as client:
        print("Sending prompt to LLM...")
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            print(f"Error: {resp.status_code} - {resp.text}")
            return None
            
        res_json = resp.json()
        job_id = res_json.get("data", {}).get("generationHistoryId")
        if not job_id:
            print("Failed to get job ID.")
            return None
            
        print(f"Job initiated (ID: {job_id}). Polling status...")
        poll_url = f"https://bapi.vidtory.net/generative-core/jobs/{job_id}/status"
        
        while True:
            await asyncio.sleep(2.0)
            poll_resp = await client.get(poll_url, headers=headers)
            status_json = poll_resp.json()
            status = status_json.get("data", {}).get("status")
            if status == "COMPLETED":
                result_text = status_json.get("data", {}).get("result", {}).get("text", "")
                print(f"LLM Response:\n\"{result_text.strip()}\"")
                return result_text.strip()
            elif status == "FAILED":
                print(f"LLM Job Failed: {status_json.get('data', {}).get('error')}")
                return None

async def test_image_tool(image_prompt):
    print("\n--- 2. Testing Image Generation Tool ---")
    tool = ImageGenerationTool(
        workspace=WORKSPACE,
        config=ImageGenerationToolConfig(enabled=True, provider="vidtory"),
        provider_configs={"vidtory": ProviderConfig(api_key=API_KEY)},
    )
    
    print(f"Generating image with prompt: \"{image_prompt}\"")
    result = await tool.execute(prompt=image_prompt, aspect_ratio="16:9")
    try:
        data = json.loads(result)
        artifact = data["artifacts"][0]
        print(f"Image successfully generated!")
        print(f"Artifact ID: {artifact['id']}")
        print(f"Local Path: {artifact['path']}")
        return artifact["path"]
    except Exception as e:
        print(f"Image generation failed: {result} - Exception: {e}")
        return None

async def test_video_tool(video_prompt, reference_image_path=None):
    print("\n--- 3. Testing Video Generation Tool ---")
    tool = VideoGenerationTool(
        workspace=WORKSPACE,
        config=VideoGenerationToolConfig(enabled=True, provider="vidtory"),
        provider_config=ProviderConfig(api_key=API_KEY),
    )
    
    print(f"Generating video with prompt: \"{video_prompt}\"")
    kwargs = {}
    if reference_image_path:
        # Convert absolute path to relative to workspace to test resolve logic
        rel_path = os.path.relpath(reference_image_path, WORKSPACE)
        kwargs["reference_images"] = [rel_path]
        print(f"Using reference image: {rel_path}")
        
    result = await tool.execute(prompt=video_prompt, aspect_ratio="16:9", duration=8, **kwargs)
    try:
        data = json.loads(result)
        artifact = data["artifacts"][0]
        print(f"Video successfully generated!")
        print(f"Artifact ID: {artifact['id']}")
        print(f"Local Path: {artifact['path']}")
        return artifact["path"]
    except Exception as e:
        print(f"Video generation failed: {result} - Exception: {e}")
        return None

async def test_audio_tool():
    print("\n--- 4. Testing Audio (TTS) Generation Tool ---")
    tool = AudioGenerationTool(
        workspace=WORKSPACE,
        config=AudioGenerationToolConfig(enabled=True, provider="vidtory"),
        provider_config=ProviderConfig(api_key=API_KEY),
    )
    
    script = "Chào mừng bạn đến với Vidtory Agent, giải pháp sáng tạo nội dung đa phương tiện sử dụng trí tuệ nhân tạo."
    print(f"Generating speech for script: \"{script}\"")
    result = await tool.execute(prompt=script, language_code="vi")
    try:
        data = json.loads(result)
        artifact = data["artifacts"][0]
        print(f"Audio successfully generated!")
        print(f"Artifact ID: {artifact['id']}")
        print(f"Local Path: {artifact['path']}")
        return artifact["path"]
    except Exception as e:
        print(f"Audio generation failed: {result} - Exception: {e}")
        return None

async def main():
    print("====================================================")
    print("Vidtory-Agent Deployment and End-to-End Test")
    print("====================================================")
    
    # 1. Test LLM
    llm_prompt = await test_llm_system()
    if not llm_prompt:
        print("Aborting test due to LLM failure.")
        return
        
    # 2. Test Image Gen
    img_path = await test_image_tool(llm_prompt)
    
    # 3. Test Video Gen (using the generated image as a starting frame/reference)
    video_prompt = "A slow cinematic panning shot of the neon city in the rain."
    await test_video_tool(video_prompt, reference_image_path=img_path)
    
    # 4. Test Audio Gen
    await test_audio_tool()
    
    print("\n====================================================")
    print("All tests completed successfully!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(main())
