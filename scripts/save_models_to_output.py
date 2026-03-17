"""
Kaggle → Local: Lưu models ra notebook output để download.
Chạy trên Kaggle. Sau đó tải output về từ Kaggle UI.

Cách dùng:
  1. Chạy script này trên Kaggle notebook
  2. Khi xong → vào notebook → Output tab → Download All
  
Lưu ý: Kaggle output limit ~20GB/notebook.
  - 4B: 8.5GB ✅
  - 9B: 17.5GB ✅  
  - Tổng: 26GB → Chạy 2 lần, mỗi lần 1 model.
  
  Lần 1: python save_models_to_output.py --model 4b
  Lần 2: python save_models_to_output.py --model 9b
"""
import os
import sys
import shutil
import tarfile
import time

MODELS = {
    "4b": {
        "src": "/root/dokichat/models/qwen3.5-4b-davidau",
        "name": "qwen3.5-4b-davidau",
        "label": "4B Chat",
    },
    "9b": {
        "src": "/root/dokichat/models/qwen3.5-9b-davidau",
        "name": "qwen3.5-9b-davidau",
        "label": "9B Chargen",
    },
}

OUTPUT_DIR = "/kaggle/working"


def tar_model(src_dir: str, name: str, label: str):
    tar_path = os.path.join(OUTPUT_DIR, f"{name}.tar.gz")
    
    print(f"[{label}] Packing: {src_dir}")
    print(f"[{label}] Output:  {tar_path}")
    
    t0 = time.time()
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(src_dir, arcname=name)
    
    size_gb = os.path.getsize(tar_path) / (1024**3)
    elapsed = time.time() - t0
    print(f"[{label}] ✅ Done: {size_gb:.1f} GB in {elapsed:.0f}s")
    return tar_path


if __name__ == "__main__":
    # Parse args
    if len(sys.argv) < 3 or sys.argv[1] != "--model":
        # Default: try both
        targets = list(MODELS.keys())
    else:
        key = sys.argv[2].lower()
        if key == "all":
            targets = list(MODELS.keys())
        elif key in MODELS:
            targets = [key]
        else:
            print(f"Unknown model: {key}. Use: 4b, 9b, or all")
            sys.exit(1)
    
    print(f"🚀 Saving models to Kaggle output")
    print(f"   Models: {', '.join(targets)}")
    print(f"   Output: {OUTPUT_DIR}\n")
    
    for key in targets:
        m = MODELS[key]
        if os.path.isdir(m["src"]):
            tar_model(m["src"], m["name"], m["label"])
        else:
            print(f"[{m['label']}] ❌ Not found: {m['src']}")
    
    # Show output
    print(f"\n📦 Output files:")
    for f in os.listdir(OUTPUT_DIR):
        fp = os.path.join(OUTPUT_DIR, f)
        if os.path.isfile(fp):
            size = os.path.getsize(fp) / (1024**3)
            print(f"  {f}: {size:.1f} GB")
    
    print(f"\n→ Go to notebook Output tab → Download")
