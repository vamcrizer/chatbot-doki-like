# Cell 1: Mount Drive
from google.colab import drive
drive.mount('/content/drive')

# Cell 2: Download to LOCAL disk first, then copy to Drive
import os, time, shutil
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"  # Disable xet storage

!pip install -q huggingface_hub

from huggingface_hub import snapshot_download

LOCAL = "/content/model_tmp"
DRIVE = "/content/drive/MyDrive/models/Huihui-Qwen3-8B-abliterated-v2"

# Step 1: Download to local (fast, stable)
print("⏳ Downloading to Colab disk...")
t0 = time.time()
snapshot_download(
    "huihui-ai/Huihui-Qwen3-8B-abliterated-v2",
    local_dir=LOCAL,
    local_dir_use_symlinks=False,
)
print(f"✅ Downloaded in {time.time()-t0:.0f}s")
!du -sh {LOCAL}

# Step 2: Copy to Drive (slower but reliable)
print("⏳ Copying to Google Drive...")
t0 = time.time()
shutil.rmtree(DRIVE, ignore_errors=True)
shutil.copytree(LOCAL, DRIVE, ignore=shutil.ignore_patterns('.cache'))
print(f"✅ Copied to Drive in {time.time()-t0:.0f}s")
!du -sh {DRIVE}

# Cleanup
shutil.rmtree(LOCAL, ignore_errors=True)
print("🎉 Done! Model in Google Drive → models/Huihui-Qwen3-8B-abliterated-v2")
