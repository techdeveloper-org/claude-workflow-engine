#!/usr/bin/env python3
"""
NPU Model Downloader - Download recommended GGUF models for Intel AI Boost
Uses urllib (built-in Python) for reliable downloads without external dependencies
"""

import urllib.request
import urllib.error
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import json

# Model registry: (name, huggingface_url, file_size_gb, purpose)
RECOMMENDED_MODELS = {
    "Gemma-2-2B": {
        "url": "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q6_K.gguf",
        "size_gb": 1.6,
        "purpose": "ultra_fast_classification",
        "description": "2B parameters, optimized for NPU, lightning fast",
    },
    "Mistral-7B": {
        "url": "https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/Mistral-7B-Instruct-v0.2-Q4_K_M.gguf",
        "size_gb": 4.3,
        "purpose": "high_quality_reasoning",
        "description": "7B parameters, excellent reasoning, strong performance",
    },
    "Phi-3.5-Mini": {
        "url": "https://huggingface.co/bartowski/phi-3.5-mini-instruct-GGUF/resolve/main/phi-3.5-mini-instruct-Q6_K.gguf",
        "size_gb": 2.4,
        "purpose": "fast_medium_reasoning",
        "description": "3.8B parameters, very fast, good quality",
    },
    "Llama-3.1-8B": {
        "url": "https://huggingface.co/bartowski/Llama-3.1-8B-Instruct-GGUF/resolve/main/Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size_gb": 5.2,
        "purpose": "strong_reasoning_coding",
        "description": "8B parameters, excellent for complex tasks and coding",
    },
    "Qwen2.5-7B": {
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "size_gb": 4.7,
        "purpose": "agentic_coding_reasoning",
        "description": "7B parameters, optimized for agentic tasks, strong coding",
    },
}

class NPUModelDownloader:
    def __init__(self, models_dir: str = "C:/Users/techd/Downloads/intel-ai/models/npu"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def get_existing_models(self) -> List[str]:
        """Get list of already downloaded models."""
        existing = [f.name for f in self.models_dir.glob("*.gguf")]
        return existing

    def get_available_space_gb(self) -> float:
        """Check available disk space."""
        import shutil
        stat = shutil.disk_usage(self.models_dir)
        return stat.free / (1024 ** 3)

    def download_file(self, url: str, dest_path: Path) -> bool:
        """Download file using urllib with progress."""
        try:
            print(f"\n📥 Downloading: {dest_path.name}")
            print(f"   URL: {url}")

            class ProgressBar:
                def __init__(self):
                    self.downloaded = 0
                    self.total = None

                def __call__(self, block_num, block_size, total_size):
                    self.total = total_size
                    self.downloaded = block_num * block_size

                    if total_size > 0:
                        percent = min(100, (self.downloaded / total_size) * 100)
                        mb_downloaded = self.downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        print(f"   Progress: {percent:.1f}% ({mb_downloaded:.1f}MB / {mb_total:.1f}MB)", end="\r")

            progress = ProgressBar()
            urllib.request.urlretrieve(url, str(dest_path), progress)

            # Verify file exists and has content
            if dest_path.exists() and dest_path.stat().st_size > 100:
                print(f"\n✅ Downloaded: {dest_path.name}")
                return True
            else:
                print(f"\n❌ Download incomplete or file is corrupt")
                dest_path.unlink(missing_ok=True)
                return False

        except urllib.error.HTTPError as e:
            print(f"\n❌ HTTP Error: {e.code} - {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"\n❌ URL Error: {e.reason}")
            return False
        except Exception as e:
            print(f"\n❌ Download error: {e}")
            dest_path.unlink(missing_ok=True)
            return False

    def run(self):
        """Main download workflow."""
        print("=" * 70)
        print("NPU MODEL DOWNLOADER - Intel AI Boost")
        print("=" * 70)

        # Check existing
        existing = self.get_existing_models()
        print(f"\n📦 Existing models ({len(existing)}):")
        for model in existing:
            size_gb = (self.models_dir / model).stat().st_size / (1024**3)
            print(f"  ✅ {model} ({size_gb:.2f}GB)")

        # Calculate what to download
        available_gb = self.get_available_space_gb()
        print(f"\n💾 Available disk space: {available_gb:.1f}GB")

        # Select models to download
        to_download = []
        total_size = 0

        print(f"\n🎯 Recommended models to add:")
        for i, (model_name, model_info) in enumerate(RECOMMENDED_MODELS.items(), 1):
            file_name = model_info["url"].split("/")[-1]

            # Check if already exists
            already_exists = any(file_name in existing_model for existing_model in existing)

            if already_exists:
                print(f"  {i}. {model_name}: {model_info['size_gb']}GB - ✅ Already exists")
            else:
                total_size += model_info["size_gb"]
                to_download.append((model_name, model_info))
                print(f"  {i}. {model_name}: {model_info['size_gb']}GB - ⬇️  Will download")

        if not to_download:
            print("\n✅ All recommended models already downloaded!")
            return

        print(f"\n📊 Summary:")
        print(f"   Models to download: {len(to_download)}")
        print(f"   Total size: {total_size:.1f}GB")
        print(f"   Available: {available_gb:.1f}GB")

        if total_size > available_gb:
            print(f"\n❌ Not enough space! Need {total_size:.1f}GB, have {available_gb:.1f}GB")
            print(f"   Delete old models or free up disk space")
            return

        # Confirm
        response = "yes"  # Default to yes
        try:
            if sys.stdin.isatty():
                response = input(f"\n⬇️  Download {len(to_download)} models? (yes/no): ").lower()
            else:
                print(f"\n⬇️  Auto-proceeding with download of {len(to_download)} models (non-interactive mode)")
                response = "yes"
        except (EOFError, KeyboardInterrupt):
            response = "yes"

        if response not in ["yes", "y"]:
            print("Cancelled.")
            return

        # Download each model
        print("\n" + "=" * 70)
        print("DOWNLOADING MODELS")
        print("=" * 70)

        successful = []
        failed = []

        for model_name, model_info in to_download:
            file_name = model_info["url"].split("/")[-1]
            dest_path = self.models_dir / file_name

            success = self.download_file(model_info["url"], dest_path)

            if success and dest_path.exists():
                size_gb = dest_path.stat().st_size / (1024 ** 3)
                successful.append((model_name, size_gb))
                print(f"   Size: {size_gb:.2f}GB")
            else:
                failed.append(model_name)

        # Summary
        print("\n" + "=" * 70)
        print("DOWNLOAD SUMMARY")
        print("=" * 70)

        if successful:
            print(f"\n✅ Successfully downloaded ({len(successful)}):")
            for name, size in successful:
                print(f"   ✅ {name} ({size:.2f}GB)")

        if failed:
            print(f"\n❌ Failed to download ({len(failed)}):")
            for name in failed:
                print(f"   ❌ {name}")
                print(f"      Try downloading manually from Hugging Face")

        # Show final status
        final_models = self.get_existing_models()
        print(f"\n📦 Total models now available: {len(final_models)}")
        for model in sorted(final_models):
            size_gb = (self.models_dir / model).stat().st_size / (1024 ** 3)
            print(f"   📄 {model} ({size_gb:.2f}GB)")

        print("\n✅ NPU is ready with available models!")
        print("   System will auto-select best model for each task")


if __name__ == "__main__":
    downloader = NPUModelDownloader()
    downloader.run()
