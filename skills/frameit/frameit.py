import argparse
import base64
import json
import os
import requests
from datetime import datetime


def generate_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def download_image(url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if url.startswith("data:"):
        header, encoded = url.split(",", 1)
        with open(path, "wb") as f:
            f.write(base64.b64decode(encoded))
    else:
        response = requests.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download image from {url}: {response.status_code}")
        with open(path, "wb") as f:
            f.write(response.content)


def upload_image(image_path):
    import fal_client
    with open(image_path, "rb") as f:
        return fal_client.upload(f, "image/png")


def generate_image(prompt, fal_key):
    url = "https://fal.run/fal-ai/flux/schnell"
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    data = {
        "prompt": prompt,
        "image_size": "landscape_16_9",
        "num_inference_steps": 4,
        "sync_mode": True,
        "output_format": "png",
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["images"][0]["url"]


def edit_image(image_path, prompt, fal_key):
    image_url = upload_image(image_path)
    url = "https://fal.run/fal-ai/flux/dev/image-to-image"
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    data = {
        "image_url": image_url,
        "prompt": prompt,
        "strength": 0.95,
        "num_inference_steps": 40,
        "sync_mode": True,
        "output_format": "png",
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["images"][0]["url"]


def upscale_image(image_url, fal_key):
    url = "https://fal.run/fal-ai/aura-sr"
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    data = {
        "image_url": image_url,
        "upscale_factor": 4,
        "checkpoint": "v2",
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["image"]["url"]


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def find_last_small_image(images_dir):
    candidates = [
        os.path.join(images_dir, f)
        for f in os.listdir(images_dir)
        if f.endswith(".png") and "_upscaled" not in f
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def main():
    parser = argparse.ArgumentParser(description="Generate or edit images using fal.ai models.")
    parser.add_argument("prompt", help="Text prompt for generation or edit description")
    parser.add_argument(
        "--edit",
        metavar="IMAGE_PATH",
        help="Path to the small (non-upscaled) image to edit. If omitted, the most recent small image is used when --mode=edit.",
    )
    parser.add_argument(
        "--mode",
        choices=["gen", "edit"],
        default="gen",
        help="Mode: 'gen' for text-to-image (default), 'edit' for image-to-image",
    )
    parser.add_argument(
        "--save-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "..", "images"),
        help="Directory to save outputs (default: images/ at project root)",
    )
    parser.add_argument(
        "--original-prompt",
        help="The raw user prompt before improvement (stored in JSON alongside the improved prompt)",
    )
    args = parser.parse_args()

    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise ValueError("FAL_KEY environment variable is not set.")

    save_dir = os.path.realpath(args.save_dir)
    os.makedirs(save_dir, exist_ok=True)
    timestamp = generate_timestamp()

    small_path = os.path.join(save_dir, f"{timestamp}.png")
    upscaled_path = os.path.join(save_dir, f"{timestamp}_upscaled.png")
    json_path = os.path.join(save_dir, f"{timestamp}.json")

    if args.mode == "gen":
        print(f"Generating image for prompt: {args.prompt}")
        generated_url = generate_image(args.prompt, fal_key)
        download_image(generated_url, small_path)
        print(f"Saved small image: {small_path}")

        print("Upscaling...")
        upscaled_url = upscale_image(generated_url, fal_key)
        download_image(upscaled_url, upscaled_path)
        print(f"Saved upscaled image: {upscaled_path}")

    elif args.mode == "edit":
        source_path = args.edit
        if not source_path:
            source_path = find_last_small_image(save_dir)
            if not source_path:
                raise RuntimeError("No small image found to edit. Use --edit to specify one.")
            print(f"Using most recent small image: {source_path}")

        if "_upscaled" in os.path.basename(source_path):
            raise ValueError("Never edit upscaled images. Provide the small version instead.")

        print(f"Editing image: {source_path}")
        edited_url = edit_image(source_path, args.prompt, fal_key)
        download_image(edited_url, small_path)
        print(f"Saved edited image: {small_path}")

        print("Upscaling...")
        upscaled_url = upscale_image(edited_url, fal_key)
        download_image(upscaled_url, upscaled_path)
        print(f"Saved upscaled image: {upscaled_path}")

    metadata = {
        "timestamp": timestamp,
        "mode": args.mode,
        "original_prompt": args.original_prompt or args.prompt,
        "prompt": args.prompt,
        "small": small_path,
        "upscaled": upscaled_path,
    }
    if args.mode == "edit" and (args.edit or find_last_small_image(save_dir)):
        metadata["source_image"] = args.edit or find_last_small_image(save_dir)

    save_json(metadata, json_path)
    print(f"Saved metadata: {json_path}")
    print(f"Done. Upscaled image at: {upscaled_path}")


if __name__ == "__main__":
    main()
