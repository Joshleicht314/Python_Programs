#!/usr/bin/env python3
import pathlib
import shutil
import ffmpeg
from PIL import Image
import pillow_heif
from tqdm import tqdm

####  How to use ####

## Make sure you are in a virtual environment with the following libraries installed:
# sudo apt update
# sudo apt install -y ffmpeg exfatprogs gvfs-backends gvfs-fuse
# sudo apt install -y ifuse libimobiledevice6 libimobiledevice-utils

# pip install pillow pillow-heif ffmpeg-python tqdm

## To mount iphone to ubuntu use the following commands
# idevicepair pair
# **** Select trust on the iphone and make the following directory if it does not exist
# mkdir ~/iPhone 
# ifuse ~/iPhone

## Copy files from DCIM folders in iPhone to local device
# Must copy to local device before running

### TO RUN ### (Ensure virtual enviornment is running)
# python convert_media.py /path/to/input /path/to/output

def convert_media(input_folder, output_folder):
    pillow_heif.register_heif_opener()
    input_folder = pathlib.Path(input_folder)
    output_folder = pathlib.Path(output_folder)

    all_files = list(input_folder.rglob("*"))  # recursive
    files = [f for f in all_files if f.is_file()]

    for f in tqdm(files, desc="Processing files"):
        # Mirror subfolder structure
        relative_path = f.relative_to(input_folder)
        out_file = output_folder / relative_path
        out_file.parent.mkdir(parents=True, exist_ok=True)

        ext = f.suffix.lower()

        try:
            # HEIF → JPG
            if ext in (".heic", ".heif"):
                out_file = out_file.with_suffix(".jpg")
                img = Image.open(f)
                img.convert("RGB").save(out_file, "JPEG")

            # MOV → MP4
            elif ext == ".mov":
                out_file = out_file.with_suffix(".mp4")
                (
                    ffmpeg
                    .input(str(f))
                    .output(str(out_file), vcodec="libx264", acodec="aac")
                    .run(overwrite_output=True, quiet=True)
                )

            # Other files → copy as-is
            else:
                shutil.copy2(f, out_file)

        except Exception as e:
            print(f"⚠️ Error processing {f}: {e}")

    print(f"\n✅ Done! All converted files saved under: {output_folder}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Recursively convert HEIF→JPG and MOV→MP4 from an input folder."
    )
    parser.add_argument("input", help="Path to input folder")
    parser.add_argument("output", help="Path to output folder (will be created if missing)")
    args = parser.parse_args()

    convert_media(args.input, args.output)
