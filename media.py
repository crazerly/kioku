import os, shutil, uuid

def media_dir():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base_dir, "media")
    os.makedirs(folder, exist_ok=True)
    return folder

ALLOWED_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def copy_media_file(src_path):
    src_path = os.path.abspath(src_path)
    base, ext = os.path.splitext(src_path)
    ext = ext.lower()
    if ext not in ALLOWED_FORMATS:
        raise ValueError("Unsupported media type")
    new_name = f"{uuid.uuid4().hex}{ext}" # generates random string
    dest_path = os.path.join(media_dir(), new_name)
    shutil.copy(src_path, dest_path) # copies file into 'media' dir
    return new_name
