import os
import shutil
import datetime

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dest = os.path.join(BACKUP_DIR, f"chroma_db_backup_{timestamp}.zip")
    src = os.path.abspath(os.path.join(CHROMA_DIR))
    if not os.path.exists(src):
        print("No chroma_db/ directory to back up.")
        return
    shutil.make_archive(dest.replace(".zip", ""), "zip", src)
    print(f"Created backup: {dest}")


if __name__ == "__main__":
    main()
