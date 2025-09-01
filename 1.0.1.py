import pystyle
import asyncio
import time
import aiohttp
import aiofiles
import os
from zipfile import ZipFile
import sys
import logging
import requests
import json
import hashlib
from threading import Lock
from datetime import datetime
os.system('cls' if os.name == 'nt' else 'clear')

logging.basicConfig(
    level=logging.INFO,
    filename="scraper.log",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

HEADERS = {'User-Agent': 'Yiffscraper v4.1.0 CLI (by axo!)'}
BASE_URL = "https://e621.net/posts.json?tags={}&limit={}"
HISTORY_FILE = "download_history.json"

class ProgressBar:
    def __init__(self, total, width=50):
        self.total = total
        self.width = width
        self.current = 0
        self.start_time = time.time()
        
    def update(self, current):
        self.current = current
        percentage = (current / self.total) * 100 if self.total > 0 else 0
        filled = int(self.width * current / self.total) if self.total > 0 else 0
        bar = '█' * filled + '░' * (self.width - filled)
        
        elapsed = time.time() - self.start_time
        if elapsed > 0 and current > 0:
            speed = current / elapsed
            eta = (self.total - current) / speed if speed > 0 else 0
            eta_str = f"ETA: {int(eta)}s"
        else:
            eta_str = "ETA: --"
            
        print(f"\r[{bar}] {percentage:6.1f}% ({current}/{self.total}) {eta_str}", end='', flush=True)
        
    def finish(self):
        self.update(self.total)
        print()  

class DownloadTracker:
    def __init__(self):
        self.downloaded_size = 0
        self.total_estimated_size = 0
        self.download_speed = 0
        self.start_time = None
        self.last_update_time = None
        self.last_downloaded_size = 0
        self.lock = Lock()
        
    def update_size(self, file_size):
        with self.lock:
            self.downloaded_size += file_size
            current_time = time.time()
            
            if self.start_time is None:
                self.start_time = current_time
                self.last_update_time = current_time
                
            
            if current_time - self.last_update_time >= 1.0:
                time_diff = current_time - self.last_update_time
                size_diff = self.downloaded_size - self.last_downloaded_size
                self.download_speed = size_diff / time_diff
                self.last_update_time = current_time
                self.last_downloaded_size = self.downloaded_size
    
    def get_stats(self):
        with self.lock:
            downloaded_mb = self.downloaded_size / (1024 * 1024)
            speed_mb = self.download_speed / (1024 * 1024)
            return downloaded_mb, speed_mb

class DownloadHistory:
    def __init__(self, history_file=HISTORY_FILE):
        self.history_file = history_file
        self.history = self.load_history()

    def load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
        return []

    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_entry(self, query_tags, count, total_size, duration, folder_name, skipped_duplicates=0):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'query_tags': query_tags,
            'file_count': count,
            'total_size_bytes': total_size,
            'duration_seconds': duration,
            'folder_name': folder_name,
            'avg_speed_mbps': (total_size / (1024 * 1024)) / (duration / 60) if duration > 0 else 0,
            'skipped_duplicates': skipped_duplicates
        }
        self.history.append(entry)
        self.save_history()

class DuplicateDetector:
    def __init__(self, download_folder):
        self.download_folder = download_folder
        self.file_hashes = {}
        self.load_existing_hashes()

    def get_file_hash(self, filepath):
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return None

    def get_data_hash(self, data):
        return hashlib.md5(data).hexdigest()

    def load_existing_hashes(self):
        if not os.path.exists(self.download_folder):
            return

        for filename in os.listdir(self.download_folder):
            filepath = os.path.join(self.download_folder, filename)
            if os.path.isfile(filepath):
                file_hash = self.get_file_hash(filepath)
                if file_hash:
                    self.file_hashes[file_hash] = filename

    def is_duplicate(self, data, post_id):
        data_hash = self.get_data_hash(data)
        if data_hash in self.file_hashes:
            return True, self.file_hashes[data_hash]
        return False, None

    def add_hash(self, data, filename):
        data_hash = self.get_data_hash(data)
        self.file_hashes[data_hash] = filename

def safe_input_password(prompt):
    """
    Safe password input that works across different environments.
    Falls back to regular input if secure input methods fail.
    Suppresses getpass warnings.
    """
    print(f"{prompt}", end='', flush=True)
    
    
    try:
        import termios
        import tty
        
        
        old_settings = termios.tcgetattr(sys.stdin)
        
        password = ""
        tty.setraw(sys.stdin.fileno())
        
        try:
            while True:
                char = sys.stdin.read(1)
                
                if ord(char) == 13 or ord(char) == 10:  
                    break
                elif ord(char) == 127 or ord(char) == 8:  
                    if password:
                        password = password[:-1]
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                elif ord(char) == 3:  
                    raise KeyboardInterrupt
                elif ord(char) >= 32 and ord(char) <= 126:  
                    password += char
                    sys.stdout.write('*')
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            print()
            
        return password
        
    except Exception:
        pass  
    
    
    if os.name == 'nt':
        try:
            import msvcrt
            password = ""
            
            while True:
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    
                    if char == b'\r':  
                        break
                    elif char == b'\x08':  
                        if password:
                            password = password[:-1]
                            print('\b \b', end='', flush=True)
                    elif char == b'\x03':  
                        raise KeyboardInterrupt
                    elif 32 <= ord(char) <= 126:  
                        password += char.decode('utf-8')
                        print('*', end='', flush=True)
            
            print()
            return password
            
        except Exception:
            pass  
    
    
    try:
        import warnings
        import getpass
        
        
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=getpass.GetPassWarning)
            password = getpass.getpass("")
            return password
            
    except Exception:
        pass  
    
    
    
    password = input("").strip()
    return password

def sanitize_folder_name(name):
    """
    Sanitize folder name for iOS/mobile compatibility.
    Removes problematic characters and handles leading dots.
    """
    
    name = name.replace(" ", "_").replace(":", "-").replace("\\", "-").replace("/", "-").replace("*", "-").replace('"', "'").replace("|", "-").replace("<", "-").replace(">", "-").replace("?", "-")
    
    
    if name.startswith("."):
        name = "dot_" + name[1:]  
    
    
    if not name:
        name = "unnamed_folder"
    
    return name

async def download_file(sem, file_url, post_id, session, download_folder, debug=False, auth=None, cookies=None, tracker=None, duplicate_detector=None, skip_duplicates=True, progress_callback=None):
    async with sem:
        try:
            if debug:
                print(f"\n[DEBUG] Downloading post {post_id} from {file_url}")

            async with session.get(file_url, headers=HEADERS, auth=auth, cookies=cookies) as response:
                if response.status == 200:
                    ext = file_url.split('.')[-1]
                    fname = f"{post_id}.{ext}"
                    path = os.path.join(download_folder, fname)
                    data = await response.read()

                    
                    if duplicate_detector and skip_duplicates:
                        is_dup, existing_file = duplicate_detector.is_duplicate(data, post_id)
                        if is_dup:
                            if debug:
                                print(f"\n[DEBUG] Skipping duplicate {post_id} (matches {existing_file})")
                            return "duplicate"

                    
                    file_size = len(data)
                    if tracker:
                        tracker.update_size(file_size)

                    async with aiofiles.open(path, 'wb') as f:
                        await f.write(data)

                    
                    if duplicate_detector:
                        duplicate_detector.add_hash(data, fname)

                    if debug:
                        print(f"\n[DEBUG] Saved {fname} ({file_size} bytes)")
                    
                    if progress_callback:
                        progress_callback()
                        
                    return "completed"
                else:
                    if debug:
                        print(f"\n[DEBUG] HTTP {response.status} for post {post_id}")
                    return "error"
        except Exception as e:
            if debug:
                print(f"\n[DEBUG] Exception {e}")
            return "error"

async def start_scraper(query_tags, total_images, thread_limit, download_folder, debug=False, auth=None, cookies=None, tracker=None, duplicate_detector=None, skip_duplicates=True):
    os.makedirs(download_folder, exist_ok=True)
    sem = asyncio.Semaphore(thread_limit)
    downloaded = 0
    skipped_duplicates = 0
    page = 1

    def update_progress():
        nonlocal downloaded
        downloaded += 1

    async with aiohttp.ClientSession(auth=auth, cookies=cookies) as session:
        while downloaded < total_images:
            batch = min(320, total_images - downloaded)
            params = {
                "tags": query_tags,
                "limit": str(batch),
                "page": str(page)
            }

            if debug:
                print(f"\n[DEBUG] GET posts.json → params={params!r}")

            async with session.get(
                    "https://e621.net/posts.json",
                    params=params,
                    headers=HEADERS
            ) as resp:
                if resp.status != 200:
                    if debug:
                        print(f"\n[DEBUG] HTTP {resp.status} — stopping")
                    break
                data = await resp.json()

            posts = data.get("posts", [])
            if not posts:
                if debug:
                    print(f"\n[DEBUG] No posts on page {page} — stopping")
                break

            
            tasks = []
            for post in posts:
                file_url = post.get("file", {}).get("url") or post.get("sample", {}).get("url")
                if file_url:
                    tasks.append(download_file(
                        sem, file_url, post["id"], session,
                        download_folder, debug, auth, cookies,
                        tracker, duplicate_detector, skip_duplicates,
                        update_progress
                    ))

            if not tasks:
                if debug:
                    print(f"\n[DEBUG] No download URLs found on page {page} — stopping")
                break

            if debug:
                print(f"\n[DEBUG] Page {page}: scheduling {len(tasks)} downloads")

            results = await asyncio.gather(*tasks)

            
            for result in results:
                if result == "duplicate":
                    skipped_duplicates += 1

            if debug:
                print(f"\n[DEBUG] Total downloaded: {downloaded}, Skipped duplicates: {skipped_duplicates}")

            
            if len(posts) < batch:
                if debug:
                    print(f"\n[DEBUG] Only {len(posts)} posts on page {page} (<{batch}) — done")
                break

            page += 1
            await asyncio.sleep(1)  

        if debug:
            print("\n[DEBUG] Scraping complete.")

        return downloaded, skipped_duplicates

def zip_folder(src_folder, dest_zip_file):
    with ZipFile(dest_zip_file, 'w') as zipf:
        for foldername, _, filenames in os.walk(src_folder):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, src_folder)
                zipf.write(filepath, arcname)

def format_size(bytes_size):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def get_credentials():
    """Get login credentials from user"""
    print()
    print()
    print("=== Auth ===")
    print("----------")
    print("| 1. Yes |")
    print("| 2. No  |")
    print("----------")
    print("Do you want to log in via API key")
    choice = input(f">> {pystyle.Colors.green}").strip()
    
    if choice == "1":
        print()
        print()

        username = input(f"{pystyle.Colors.reset}Username: {pystyle.Colors.red}").strip()
        api_key = safe_input_password(f"{pystyle.Colors.reset}API Key:  {pystyle.Colors.red}")
        
        if not username or not api_key:
            print("[CONTINUE] Both username and API key are required.")
            time.sleep(2)
            return None, None
            
        
        print("[DEBUG] Testing credentials...")
        test_url = "https://e621.net/posts.json?tags=rating:safe&limit=1"
        auth = (username, api_key)
        r = requests.get(test_url, auth=auth, headers=HEADERS)
        
        if r.status_code == 200:
            print(f"[DEBUG] Successfully logged in as '{username}'")
            time.sleep(1)
            return username, api_key
        else:
            print(f"[DEBUG] Authentication failed (HTTP {r.status_code})")
            time.sleep(1)
            return None, None
    else:
        print("[DEBUG] Proceeding without authentication")
        time.sleep(1)
        return None, None

def get_download_options():
    os.system('cls' if os.name == 'nt' else 'clear')
    show_banner()
    """Get download options from user"""
    print()
    print()
    print(f"=== Download ===")
    
    
    tags = input(f"Enter tags (space-separated): {pystyle.Colors.green}").strip()
    if not tags:
        print("Tags are required!")
        time.sleep(2)
        return None
        
    
    while True:
        try:
            post_count = int(input(f"{pystyle.Colors.reset}Number of posts to download: {pystyle.Colors.green}").strip())
            if post_count <= 0:
                print("[INFO] Post count must be positive!")
                continue
            break
        except ValueError:
            print("[RETRY] Please enter a valid number!")
    
    
    while True:
        try:
            thread_count = int(input(f"{pystyle.Colors.reset}Number of threads (default 5): {pystyle.Colors.green}").strip() or "5")
            if thread_count <= 0:
                print("[INFO] Thread count must be positive!")
                continue
            break
        except ValueError:
            print("[RETRY] Please enter a valid number!")
    
    
    folder_name = sanitize_folder_name(tags)
    
    
    zip_choice = input(f"{pystyle.Colors.reset}Zip folder after download? (y/N): {pystyle.Colors.green}").strip().lower() in ['y', 'yes']
    
    
    skip_duplicates = input(f"{pystyle.Colors.reset}Skip duplicate files? (Y/n): {pystyle.Colors.green}").strip().lower() not in ['n', 'no']
    
    
    debug = input(f"{pystyle.Colors.reset}Enable debug mode? (y/N): {pystyle.Colors.green}").strip().lower() in ['y', 'yes']
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{pystyle.Colors.red}")
    for i in range(1,2):
        print("\rStarting... █░░░", end="")
        time.sleep(0.05)
        print("\rStarting... ██░░", end="")
        time.sleep(0.05)
        print("\rStarting... ███░", end="")
        time.sleep(0.05)
        print("\rStarting... ████", end="")
        time.sleep(0.05)
    #print(f"{pystyle.Colors.light_blue}\r              ")
    print(f"{pystyle.Colors.gray}\r                                     ")

    return {
        'tags': tags,
        'post_count': post_count,
        'thread_count': thread_count,
        'folder_name': folder_name,
        'zip_folder': zip_choice,
        'skip_duplicates': skip_duplicates,
        'debug': debug
    }

def estimate_total_size(query_tags, post_count, auth=None):
    """Estimate total download size by sampling posts"""
    try:
        url = f"https://e621.net/posts.json?tags={query_tags}&limit=10"
        r = requests.get(url, auth=auth, headers=HEADERS)
        
        if r.status_code == 200:
            data = r.json()
            posts = data.get('posts', [])
            if posts:
                total_sample_size = 0
                valid_posts = 0
                
                for post in posts:
                    file_info = post.get('file', {})
                    if file_info.get('size'):
                        total_sample_size += file_info['size']
                        valid_posts += 1
                
                if valid_posts > 0:
                    avg_size = total_sample_size / valid_posts
                    estimated_total = avg_size * post_count
                    return estimated_total
    except Exception as e:
        print(f"Error estimating size: {e}")
    
    return 0

async def run_cli_scraper(options, username=None, api_key=None):
    """Main scraper function for CLI"""
    download_folder = os.path.join("Folders", options['folder_name'])
    os.makedirs(download_folder, exist_ok=True)
    
    
    auth = None
    if username and api_key:
        auth = aiohttp.BasicAuth(username, api_key)
    
    
    tracker = DownloadTracker()
    duplicate_detector = DuplicateDetector(download_folder)
    progress_bar = ProgressBar(options['post_count'])
    history = DownloadHistory()
    
    print(f"\n=== Starting Download ===")
    print(f"Tags: {options['tags']}")
    print(f"posts: {options['post_count']}")
    print(f"Threads: {options['thread_count']}")
    print(f"Folder: {download_folder}")
    print(f"Skip duplicates: {options['skip_duplicates']}")
    
    
    if auth:
        estimated_size = estimate_total_size(options['tags'], options['post_count'], (username, api_key))
    else:
        estimated_size = estimate_total_size(options['tags'], options['post_count'])
    
    if estimated_size > 0:
        print(f"Estimated download size: {format_size(estimated_size)}")
    
    print()  
    
    
    start_time = time.time()
    
    
    def progress_reporter():
        while progress_bar.current < progress_bar.total:
            downloaded_mb, speed_mb = tracker.get_stats()
            if downloaded_mb > 0:
                print(f"\nDownloaded: {format_size(tracker.downloaded_size)} | Speed: {speed_mb:.1f} MB/s")
            time.sleep(2)
    
    import threading
    progress_thread = threading.Thread(target=progress_reporter, daemon=True)
    progress_thread.start()
    
    
    downloaded_count, skipped_count = await start_scraper(
        query_tags=options['tags'],
        total_images=options['post_count'],
        thread_limit=options['thread_count'],
        download_folder=download_folder,
        debug=options['debug'],
        auth=auth,
        tracker=tracker,
        duplicate_detector=duplicate_detector,
        skip_duplicates=options['skip_duplicates']
    )
    
    
    progress_bar.finish()
    
    
    end_time = time.time()
    duration = end_time - start_time
    final_size = tracker.downloaded_size
    
    
    for _ in range(25):
        print()
    
    print(f"=== Download Complete ===")
    print(f"Downloaded: {downloaded_count} files")
    print(f"Skipped duplicates: {skipped_count}")
    print(f"Total size: {format_size(final_size)}")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Average speed: {(final_size / (1024 * 1024)) / (duration / 60):.1f} MB/min")
    
    
    history.add_entry(
        query_tags=options['tags'],
        count=downloaded_count,
        total_size=final_size,
        duration=duration,
        folder_name=options['folder_name'],
        skipped_duplicates=skipped_count
    )
    
    
    if options['zip_folder']:
        print("Creating zip archive...")
        zip_folder(download_folder, download_folder + ".zip")
        print(f"[DEBUG] Created {download_folder}.zip")

def show_banner():
    print(f"{pystyle.Colors.reset}")
    """Display application banner"""
    print("==============================")
    print("    YiffScraper CLI v1.0.0    ")
    print(" Made by DD87686 on github <3 ")
    print("==============================")

def main():
    """Main CLI function"""
    show_banner()
    
    options = None  
    
    try:
        
        username, api_key = get_credentials()
        
        
        options = get_download_options()
        if not options:
            print("Invalid options provided. Exiting.")
            return
        
        
        asyncio.run(run_cli_scraper(options, username, api_key))
        
    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        if options and options.get('debug'):
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()