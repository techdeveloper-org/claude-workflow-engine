#!/usr/bin/env python3
"""
NPU Model Downloader - Download recommended GGUF models for Intel AI Boost

Recommended models:
- Gemma-2-2B: Ultra-fast, great for classification
- Mistral-7B: High quality reasoning
- Phi-3.5-Mini: Lightweight, fast inference
- Qwen2.5-7B: Optimized for local tasks
- Llama-3.1-8B: Strong reasoning capabilities
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict
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

# Keep existing models
EXISTING_MODELS = [
    "DeepSeek-R1-Distill-Qwen-1.5B-Q6_K.gguf",
    "Llama-3.2-3B-Instruct-Q6_K.gguf",
    "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
]

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

    def calculate_total_size(self, models_to_download: List[str]) -> float:
        """Calculate total size of models to download."""
        total = 0
        for model in models_to_download:
            if model in RECOMMENDED_MODELS:
                total += RECOMMENDED_MODELS[model]["size_gb"]
        return total

    def download_file(self, url: str, dest_path: Path) -> bool:
        """Download file using wget or curl."""
        try:
            print(f"\n📥 Downloading: {dest_path.name}")
            print(f"   URL: {url}")
            print(f"   Size: ~{RECOMMENDED_MODELS.get(dest_path.stem, {}).get('size_gb', '?')}GB")

            # Try with aria2c (fastest, resumable)
            cmd = [
                "aria2c",
                "--max-connection-per-server=16",
                "--split=16",
                "--max-tries=5",
                "--auto-file-renaming=false",
                "-o",
                str(dest_path),
                url,
            ]

            result = subprocess.run(cmd, timeout=7200)  # 2 hour timeout
            if result.returncode == 0:
                print(f"✅ Downloaded: {dest_path.name}")
                return True
            else:
                print(f"⚠️  aria2c failed, trying curl...")

                # Fallback to curl
                cmd = [
                    "curl",
                    "-L",
                    "-o",
                    str(dest_path),
                    "--progress-bar",
                    url,
                ]
                result = subprocess.run(cmd, timeout=7200)
                if result.returncode == 0:
                    print(f"✅ Downloaded: {dest_path.name}")
                    return True

                # Last fallback: wget
                print(f"⚠️  curl failed, trying wget...")
                cmd = ["wget", "-O", str(dest_path), url]
                result = subprocess.run(cmd, timeout=7200)
                if result.returncode == 0:
                    print(f"✅ Downloaded: {dest_path.name}")
                    return True

                print(f"❌ All download methods failed")
                return False

        except subprocess.TimeoutExpired:
            print(f"❌ Download timeout (2 hours exceeded)")
            return False
        except Exception as e:
            print(f"❌ Download error: {e}")
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
            print(f"  ✅ {model}")

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
        response = input(f"\n⬇️  Download {len(to_download)} models? (yes/no): ").lower()
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

        # Show final status
        final_models = self.get_existing_models()
        print(f"\n📦 Total models now available: {len(final_models)}")
        for model in sorted(final_models):
            size_gb = (self.models_dir / model).stat().st_size / (1024 ** 3)
            print(f"   📄 {model} ({size_gb:.2f}GB)")

        # Update npu_service.py config
        self._update_config(final_models)

    def _update_config(self, available_models: List[str]):
        """Update npu_service.py with available models."""
        config_file = Path(__file__).parent / "langgraph_engine" / "npu_service.py"

        print(f"\n🔧 Updating configuration...")
        print(f"   File: {config_file}")

        # Just inform user - manual update recommended
        print(f"\n   ℹ️  Available models for inference:")
        for model in sorted(available_models):
            print(f"      - {model}")

        print(f"\n   Update npu_service.py to use these models in:")
        print(f"   - self.models dictionary")
        print(f"   - Routing logic based on complexity")


if __name__ == "__main__":
    downloader = NPUModelDownloader()
    downloader.run()
