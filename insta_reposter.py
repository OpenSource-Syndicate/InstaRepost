import json
import os
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import schedule
from colorama import Fore, Style, init
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.types import Media

# Initialize colorama
init()

# Load environment variables
load_dotenv()
USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
REPOST_CAPTION = os.getenv("REPOST_CAPTION", "Reposted")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", 30))
HISTORY_FILE = os.getenv("HISTORY_FILE", "repost_history.json")
MEDIA_FOLDER = os.getenv("MEDIA_FOLDER", "instagram_media")
COOKIES_FILE = os.getenv("COOKIES_FILE", "instagram_cookies.json")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 3))  # Number of parallel workers
# Option to keep downloaded media files instead of deleting them
KEEP_MEDIA = os.getenv("KEEP_MEDIA", "False").lower() in ("true", "1", "yes")

# Create media folder if it doesn't exist
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Create Instagram client with better timeout settings
client = Client()
client.request_timeout = 30  # Increase default timeout to 30 seconds
client.logger.setLevel("INFO")  # Set logging level

saved_posts_history = set()
history_lock = Lock()  # Lock for thread-safe history updates

# Initialize MoviePy status
MOVIEPY_AVAILABLE = False


def log_info(message):
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {message}")


def log_success(message):
    print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {message}")


def log_warning(message):
    print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} {message}")


def log_error(message):
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")


def log_debug(message):
    print(f"{Fore.BLUE}[DEBUG]{Style.RESET_ALL} {message}")


def check_dependencies():
    """Check and install required dependencies."""
    global MOVIEPY_AVAILABLE
    try:
        # Try to import required packages
        try:
            import moviepy.editor
            from PIL import Image  # Add PIL import check
            
            MOVIEPY_AVAILABLE = True
            log_success("All dependencies successfully imported!")
        except ImportError as e:
            log_warning(f"Dependency import failed: {e}. Installing required packages...")
            
            # Install required packages
            packages = [
                ("moviepy", "1.0.3"),
                ("Pillow", "latest")  # Add PIL package
            ]
            
            for package, version in packages:
                try:
                    if version == "latest":
                        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                    else:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", f"{package}=={version}"])
                except Exception as install_error:
                    log_error(f"Failed to install {package}: {install_error}")
                    return False

        log_success("All dependencies verified!")
        return True
    except Exception as e:
        log_error(f"Error checking/installing dependencies: {e}")
        log_warning("Please manually install required dependencies with:")
        log_info("pip install moviepy==1.0.3")
        return False


def load_history():
    """Load repost history from JSON file."""
    global saved_posts_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                saved_posts_history = set(json.load(f))
            log_info(f"Loaded {len(saved_posts_history)} posts from history file.")
        else:
            saved_posts_history = set()
            log_info("No history file found. Starting with empty history.")
    except Exception as e:
        log_error(f"Error loading history file: {e}")
        saved_posts_history = set()


def save_history():
    """Save repost history to JSON file."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(saved_posts_history), f)
        log_info(f"Saved {len(saved_posts_history)} posts to history file.")
    except Exception as e:
        log_error(f"Error saving history file: {e}")


def save_cookies():
    """Save Instagram cookies to file."""
    try:
        cookies = client.get_settings()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
        log_success("Cookies saved successfully!")
    except Exception as e:
        log_error(f"Error saving cookies: {e}")


def load_cookies():
    """Load Instagram cookies from file."""
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            client.set_settings(cookies)
            log_success("Cookies loaded successfully!")
            return True
        return False
    except Exception as e:
        log_error(f"Error loading cookies: {e}")
        return False


def login():
    """Login to Instagram account using cookies if available, otherwise manual login."""
    try:
        # Try to load cookies first
        if load_cookies():
            try:
                # Test if cookies are still valid using a simple API call
                log_info("Testing saved cookies...")
                # Use a simple API call that's less likely to fail
                client.get_timeline_feed()
                log_success("Login successful using saved cookies!")
                return True
            except Exception as e:
                log_warning(f"Saved cookies are invalid: {e}")
                log_warning("Proceeding with manual login...")

        # Manual login if cookies are not available or invalid
        log_info(f"Logging in as {USERNAME}...")
        try:
            verification_code = str(input("Verification Code: "))
            # Try simple login first without verification
            client.login(USERNAME, PASSWORD, verification_code=verification_code)
            log_success("Login successful!")

            # Save cookies after successful login
            save_cookies()
            return True
        except Exception as e:
            if "challenge_required" in str(e):
                log_info(
                    "Instagram requires verification. Please check your email or phone for a verification code."
                )
                verification_code = str(input("Enter verification code: "))
                try:
                    client.login(
                        USERNAME, PASSWORD, verification_code=verification_code
                    )
                    log_success("Login with verification successful!")
                    save_cookies()
                    return True
                except Exception as verify_error:
                    log_error(f"Verification failed: {verify_error}")
                    return False
            else:
                log_error(f"Login failed: {e}")
                return False
    except Exception as e:
        log_error(f"Login failed: {e}")
        return False


def get_saved_posts():
    """Get user's saved posts using various methods with fallback."""
    methods = [
        ("All Posts collection", lambda: client.collection_medias_by_name("All Posts")),
        ("Saved collection", lambda: client.collection_medias_by_name("Saved")),
        ("First collection", lambda: client.collection_medias(client.collections()[0].id) if client.collections() else None),
        ("Direct saved posts", lambda: client.user_saved_medias(client.user_id))
    ]

    for method_name, fetch_method in methods:
        try:
            log_info(f"Attempting to get saved posts from {method_name}")
            saved_posts = fetch_method()
            if saved_posts:
                log_success(f"Successfully fetched {len(saved_posts)} posts from {method_name}")
                return saved_posts
        except Exception as e:
            log_warning(f"Failed to get posts from {method_name}: {e}")
    
    log_error("All methods to fetch saved posts failed")
    return []


def handle_media_file(path, media_id, keep_media=False):
    """Common cleanup logic for media files"""
    if not keep_media and path and os.path.exists(path):
        for retry in range(3):
            try:
                os.remove(path)
                break
            except Exception as file_error:
                log_warning(f"Attempt {retry + 1}: Could not remove file {path}: {file_error}")
                time.sleep(2)
        
        # Handle thumbnail if exists
        thumbnail_path = f"{path}.jpg"
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except Exception as thumb_error:
                log_warning(f"Could not remove thumbnail: {thumb_error}")
    elif keep_media and path:
        log_info(f"Keeping downloaded media at: {path}")

def download_media(client, media_id, media_type, folder, max_retries=3):
    """Download media with retry logic"""
    for retry in range(max_retries):
        try:
            if media_type == 1:  # Photo
                path = client.photo_download(media_id, folder=folder)
            else:  # Video
                path = client.video_download(media_id, folder=folder)
            log_success(f"Downloaded {'photo' if media_type == 1 else 'video'}: {media_id}")
            return path
        except Exception as e:
            if retry < max_retries - 1:
                log_warning(f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise
    return None

def unsave_media(client, media_id):
    """Unsave media with proper logging"""
    try:
        client.media_unsave(media_id)
        log_success(f"Deleted post {media_id} from saved posts")
        return True
    except Exception as unsave_error:
        log_error(f"Failed to delete post {media_id} from saved posts: {unsave_error}")
        return False

def validate_file_format(path):
    """Validate if file has supported image extension"""
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    # Convert WindowsPath to string before calling lower()
    path_str = str(path)
    return path_str.lower().endswith(valid_extensions)

def convert_to_jpg(input_path):
    """Convert image to JPG format"""
    from PIL import Image
    try:
        img = Image.open(input_path)
        jpg_path = input_path.rsplit('.', 1)[0] + '.jpg'
        img.convert('RGB').save(jpg_path, 'JPEG')
        log_success(f"Converted image to JPG: {jpg_path}")
        return jpg_path
    except Exception as e:
        log_error(f"Failed to convert image: {e}")
        return None

class RateLimiter:
    """Simple rate limiter with exponential backoff"""
    def __init__(self, initial_delay=1, max_delay=300, backoff_factor=2):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.current_delay = initial_delay
        self.last_attempt = 0

    def wait(self):
        """Wait appropriate time between API calls"""
        now = time.time()
        time_since_last = now - self.last_attempt
        if time_since_last < self.current_delay:
            time.sleep(self.current_delay - time_since_last)
        self.last_attempt = now

    def success(self):
        """Reset delay on successful API call"""
        self.current_delay = self.initial_delay

    def failure(self):
        """Increase delay on API failure"""
        self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay)

# Create rate limiter instances for different API operations
POST_RATE_LIMITER = RateLimiter(initial_delay=2)
LIKE_RATE_LIMITER = RateLimiter(initial_delay=1)
MEDIA_RATE_LIMITER = RateLimiter(initial_delay=5)

def with_rate_limit(func, rate_limiter):
    """Decorator to apply rate limiting to a function"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                rate_limiter.wait()
                result = func(*args, **kwargs)
                rate_limiter.success()
                return result
            except Exception as e:
                rate_limiter.failure()
                if attempt < max_retries - 1:
                    log_warning(f"Rate limit exceeded, retrying in {rate_limiter.current_delay}s...")
                    time.sleep(rate_limiter.current_delay)
                else:
                    raise
    return wrapper

# Apply rate limiting to Instagram client methods
client.photo_upload = with_rate_limit(client.photo_upload, POST_RATE_LIMITER)
client.video_upload = with_rate_limit(client.video_upload, POST_RATE_LIMITER)
client.clip_upload = with_rate_limit(client.clip_upload, POST_RATE_LIMITER)
client.igtv_upload = with_rate_limit(client.igtv_upload, POST_RATE_LIMITER)
client.album_upload = with_rate_limit(client.album_upload, POST_RATE_LIMITER)
client.media_like = with_rate_limit(client.media_like, LIKE_RATE_LIMITER)
client.photo_download = with_rate_limit(client.photo_download, MEDIA_RATE_LIMITER)
client.video_download = with_rate_limit(client.video_download, MEDIA_RATE_LIMITER)

class SessionManager:
    """Manages Instagram session and handles automatic refresh"""
    def __init__(self, client, refresh_interval=3600):  # 1 hour default
        self.client = client
        self.refresh_interval = refresh_interval
        self.last_refresh = 0
        self._lock = Lock()

    def refresh_if_needed(self):
        """Refresh session if interval has passed"""
        with self._lock:
            now = time.time()
            if now - self.last_refresh > self.refresh_interval:
                try:
                    log_info("Refreshing Instagram session...")
                    # Try to make a simple API call to test session
                    self.client.get_timeline_feed()
                    self.last_refresh = now
                    log_success("Session is still valid")
                except Exception as e:
                    log_warning(f"Session refresh failed: {e}")
                    try:
                        # Try to relogin
                        if login():
                            self.last_refresh = now
                            log_success("Successfully refreshed session")
                        else:
                            log_error("Failed to refresh session")
                    except Exception as login_error:
                        log_error(f"Error during session refresh: {login_error}")

    def with_session_refresh(self, func):
        """Decorator to refresh session before API calls"""
        def wrapper(*args, **kwargs):
            self.refresh_if_needed()
            return func(*args, **kwargs)
        return wrapper

# Create session manager instance
session_manager = SessionManager(client)

# Apply session refresh to critical API operations
client.photo_upload = session_manager.with_session_refresh(client.photo_upload)
client.video_upload = session_manager.with_session_refresh(client.video_upload)
client.clip_upload = session_manager.with_session_refresh(client.clip_upload)
client.igtv_upload = session_manager.with_session_refresh(client.igtv_upload)
client.album_upload = session_manager.with_session_refresh(client.album_upload)

class ConnectionPoolManager:
    """Manages a pool of Instagram API connections"""
    def __init__(self, min_connections=2, max_connections=5):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._pool = []
        self._in_use = {}
        self._lock = Lock()
        
        # Only initialize one connection initially to avoid multiple 2FA prompts
        self._add_connection()
    
    def _add_connection(self):
        """Create a new Instagram client connection"""
        try:
            new_client = Client()
            new_client.request_timeout = 30
            
            # Try to load cookies first
            if os.path.exists(COOKIES_FILE):
                with open(COOKIES_FILE, "r") as f:
                    cookies = json.load(f)
                new_client.set_settings(cookies)
                try:
                    # Test if cookies are valid
                    new_client.get_timeline_feed()
                    self._pool.append(new_client)
                    return new_client
                except Exception:
                    pass  # If cookies fail, proceed with manual login
            
            # If no valid cookies, use the main login function
            if login():
                # After successful login, use the authenticated client from the main session
                self._pool.append(client)  # Use the global client that was authenticated
                return client
            else:
                log_error("Failed to authenticate new connection")
                return None
                
        except Exception as e:
            log_error(f"Failed to create new connection: {e}")
            return None
    
    def get_connection(self, timeout=30):
        """Get an available connection from the pool"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                # Try to get an available connection
                for client in self._pool:
                    if client not in self._in_use:
                        self._in_use[client] = time.time()
                        return client
                
                # If no connection is available and we haven't reached max, create new one
                if len(self._pool) < self.max_connections:
                    new_client = self._add_connection()
                    if new_client:
                        self._in_use[new_client] = time.time()
                        return new_client
            
            # Wait before trying again
            time.sleep(1)
        
        raise TimeoutError("Could not get a connection from the pool")
    
    def release_connection(self, client):
        """Release a connection back to the pool"""
        with self._lock:
            if client in self._in_use:
                del self._in_use[client]
    
    def cleanup_stale_connections(self, max_age=3600):
        """Remove stale connections from the pool"""
        with self._lock:
            current_time = time.time()
            stale_clients = []
            
            # Identify stale connections
            for client, start_time in self._in_use.items():
                if current_time - start_time > max_age:
                    stale_clients.append(client)
            
            # Remove stale connections
            for client in stale_clients:
                if client in self._in_use:
                    del self._in_use[client]
                if client in self._pool:
                    self._pool.remove(client)
            
            # Ensure minimum connections are maintained
            while len(self._pool) < self.min_connections:
                self._add_connection()

# Create connection pool manager instance
connection_pool = ConnectionPoolManager()

# Start periodic connection cleanup
def cleanup_connections():
    """Periodically cleanup stale connections"""
    while True:
        try:
            connection_pool.cleanup_stale_connections()
        except Exception as e:
            log_error(f"Error cleaning up connections: {e}")
        time.sleep(1800)  # Run every 30 minutes

cleanup_thread = threading.Thread(target=cleanup_connections, daemon=True)
cleanup_thread.start()

def repost_media(media: Media):
    """Repost media based on its type using connection pooling."""
    client = None
    media_id = media.id  # Define media_id at the start of the function
    try:
        client = connection_pool.get_connection()
        if media_id in saved_posts_history:
            log_info(f"Skipping already reposted media: {media_id}")
            return

        log_info(f"Processing media: {media_id}")

        # Like the post first
        try:
            client.media_like(media_id)
            log_success(f"Liked post: {media_id}")
        except Exception as e:
            log_error(f"Failed to like post {media_id}: {e}")

        caption = f"{REPOST_CAPTION}\n\nOriginal by @{media.user.username}"
        media_specific_folder = os.path.join(MEDIA_FOLDER, f"{media.user.username}_{media_id}")
        os.makedirs(media_specific_folder, exist_ok=True)

        repost_successful = False

        if media.media_type == 1:  # Photo
            path = None
            try:
                path = download_media(client, media_id, 1, media_specific_folder)
                if not validate_file_format(path):
                    jpg_path = convert_to_jpg(path)
                    if jpg_path:
                        path = jpg_path
                    else:
                        raise Exception("Failed to convert image format")

                time.sleep(2)  # Add delay before upload
                client.photo_upload(path, caption)
                log_success(f"Successfully uploaded photo: {media_id}")
                repost_successful = True
            except Exception as e:
                log_error(f"Error processing photo {media_id}: {e}")
            finally:
                if repost_successful:
                    unsave_media(client, media_id)
                handle_media_file(path, media_id, KEEP_MEDIA)

        elif media.media_type == 2:  # Video
            if not MOVIEPY_AVAILABLE:
                log_warning("MoviePy is not available. Skipping video...")
                return

            path = None
            try:
                path = download_media(client, media_id, 2, media_specific_folder)
                time.sleep(2)

                if not media.product_type:  # Regular video
                    client.video_upload(path, caption)
                elif media.product_type == "igtv":
                    client.igtv_upload(path, caption, media.title or "Reposted IGTV")
                elif media.product_type == "clips":  # Reels
                    client.clip_upload(path, caption)
                
                log_success(f"Successfully uploaded {media.product_type or 'video'}: {media_id}")
                repost_successful = True
            except Exception as e:
                log_error(f"Error processing video {media_id}: {e}")
            finally:
                if repost_successful:
                    unsave_media(client, media_id)
                handle_media_file(path, media_id, KEEP_MEDIA)

        elif media.media_type == 8:  # Album
            paths = []
            try:
                for i, resource in enumerate(media.resources):
                    resource_subfolder = os.path.join(media_specific_folder, f"item_{i}")
                    os.makedirs(resource_subfolder, exist_ok=True)
                    
                    try:
                        path = download_media(client, resource.pk, resource.media_type, resource_subfolder)
                        if path:
                            paths.append(path)
                    except Exception as e:
                        log_error(f"Failed to download resource {i} of album {media_id}: {e}")

                if paths:
                    time.sleep(2)
                    client.album_upload(paths, caption)
                    log_success(f"Successfully uploaded album: {media_id}")
                    repost_successful = True
                else:
                    log_warning("No valid media found in album")
            except Exception as e:
                log_error(f"Error processing album {media_id}: {e}")
            finally:
                if repost_successful:
                    unsave_media(client, media_id)
                for path in paths:
                    handle_media_file(path, media_id, KEEP_MEDIA)

        if repost_successful:
            saved_posts_history.add(media_id)
            save_history()
            log_success(f"Successfully reposted {media_id}")
        else:
            log_warning(f"Repost of {media_id} was not successful. Not adding to history.")
            
    except Exception as e:
        log_error(f"Error reposting media {media_id}: {e}")
    finally:
        if client:
            connection_pool.release_connection(client)


def check_api_connectivity():
    """Test if the Instagram API is responding correctly."""
    try:
        log_info("Testing Instagram API connectivity...")
        # First try a simpler API call that's less likely to fail
        try:
            user_id = client.user_id
            # Try to get the user's own profile first
            user_info = client.user_info_v1(user_id)
            log_success(
                f"API connectivity test successful! Connected as: {user_info.username}"
            )
            return True
        except Exception as e1:
            log_warning(f"Primary API test failed: {e1}")

            # Try an alternative API endpoint
            try:
                # Try timeline feed as a fallback
                client.get_timeline_feed()
                log_success("API connectivity test successful using timeline feed!")
                return True
            except Exception as e2:
                log_warning(f"Secondary API test failed: {e2}")

                # Try one more simple API call
                try:
                    client.get_reels_tray()
                    log_success("API connectivity test successful using reels tray!")
                    return True
                except Exception as e3:
                    log_error(f"All API connectivity tests failed. Last error: {e3}")
                    return False
    except Exception as e:
        log_error(f"API connectivity test failed: {e}")
        return False


def check_and_repost():
    """Check for saved posts and repost them using parallel processing."""
    try:
        # Check if client is logged in
        if not client.user_id:
            log_info("Client user_id not found, attempting login")
            if not login():
                log_error("Login failed in check_and_repost")
                return

        # Check API connectivity with retry logic
        max_api_retries = 3
        for retry in range(max_api_retries):
            if check_api_connectivity():
                break
            elif retry < max_api_retries - 1:
                log_warning(
                    f"API connectivity check failed, retry {retry + 1}/{max_api_retries}"
                )
                time.sleep(10)  # Wait before retry
            else:
                log_error(
                    "Cannot proceed with reposting due to API connectivity issues after retries"
                )
                return

        log_info("Checking for saved posts to repost...")

        # Get saved posts with retry logic
        saved_medias = []
        max_saved_retries = 3
        for retry in range(max_saved_retries):
            try:
                log_debug("Getting saved posts")
                saved_medias = get_saved_posts()
                if saved_medias:
                    break
                elif retry < max_saved_retries - 1:
                    log_warning(
                        f"No saved posts found, retry {retry + 1}/{max_saved_retries}"
                    )
                    time.sleep(5)  # Wait before retry
            except Exception as e:
                if retry < max_saved_retries - 1:
                    log_warning(
                        f"Error getting saved posts: {e}, retry {retry + 1}/{max_saved_retries}"
                    )
                    time.sleep(5)  # Wait before retry
                else:
                    raise

        log_info(f"Found {len(saved_medias)} saved posts to process")

        if not saved_medias:
            log_info("No saved posts found to repost")
            return

        # Filter out already reposted media
        to_repost = [media for media in saved_medias if media.id not in saved_posts_history]
        if not to_repost:
            log_info("All saved posts have already been reposted")
            return

        log_info(f"Processing {len(to_repost)} saved posts in parallel with {MAX_WORKERS} workers")

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_media = {executor.submit(repost_media, media): media for media in to_repost}
            
            # Process completed tasks as they finish
            for future in as_completed(future_to_media):
                media = future_to_media[future]
                try:
                    future.result()  # This will raise any exceptions that occurred
                except Exception as e:
                    log_error(f"Error processing media {media.id}: {e}")
                    import traceback
                    log_error(f"Traceback: {traceback.format_exc()}")

        log_info(f"Completed check. Next check in {CHECK_INTERVAL} minutes.")
    except Exception as e:
        log_error(f"Error in check_and_repost: {e}")
        import traceback
        log_error(f"Traceback: {traceback.format_exc()}")


def main():
    """Main function to run the reposter."""
    if not USERNAME or not PASSWORD:
        log_error("Instagram credentials not found or invalid!")
        log_info("Please create a .env file with the following content:")
        log_info("INSTAGRAM_USERNAME=your_username")
        log_info("INSTAGRAM_PASSWORD=your_password")
        log_info('REPOST_CAPTION="Reposted"')
        log_info("CHECK_INTERVAL_MINUTES=30")
        log_info("HISTORY_FILE=repost_history.json")
        log_info("MEDIA_FOLDER=instagram_media")
        log_info("KEEP_MEDIA=False  # Set to True to keep downloaded media files")
        log_info("\nOr provide these values as environment variables.")
        return

    try:
        # Check and install dependencies
        if not check_dependencies():
            log_error(
                "Required dependencies are missing. Please install them and try again."
            )
            return

        # Test if the Client initialization works properly
        log_info("Testing Instagram client initialization...")
        if not login():
            log_error(
                "Instagram client initialization failed. Please check your credentials and try again."
            )
            return

        # Load history from file
        load_history()

        log_info(f"Setting up scheduler to check every {CHECK_INTERVAL} minutes.")

        # Schedule the check
        schedule.every(CHECK_INTERVAL).minutes.do(check_and_repost)

        # Run immediately for the first time
        try:
            log_info("Running initial check_and_repost...")
            check_and_repost()
        except Exception as e:
            log_error(f"Error during initial check_and_repost: {e}")
            import traceback

            log_error(f"Traceback: {traceback.format_exc()}")

        # Keep the script running
        log_success("Instagram Auto Reposter is now running! Press Ctrl+C to stop.")
        consecutive_errors = 0
        while True:
            try:
                schedule.run_pending()
                consecutive_errors = 0  # Reset error counter on success
            except Exception as e:
                consecutive_errors += 1
                log_error(f"Error in scheduler: {e}")
                import traceback

                log_error(f"Traceback: {traceback.format_exc()}")

                # If we've had multiple consecutive errors, wait longer before retrying
                if consecutive_errors > 3:
                    log_warning(
                        f"Multiple consecutive errors ({consecutive_errors}). Waiting 5 minutes before retry."
                    )
                    time.sleep(300)  # 5 minutes
                else:
                    log_warning("Error occurred. Waiting 30 seconds before retry.")
                    time.sleep(30)

            time.sleep(1)
    except KeyboardInterrupt:
        log_info("\nStopping Instagram Auto Reposter...")
        save_history()
    except Exception as e:
        log_error(f"An unexpected error occurred: {e}")
        import traceback

        log_error(f"Traceback: {traceback.format_exc()}")
        save_history()


if __name__ == "__main__":
    main()

class MemoryManager:
    """Manages memory usage and cleanup of media files"""
    def __init__(self, media_folder, max_folder_size_mb=500):
        self.media_folder = media_folder
        self.max_folder_size_mb = max_folder_size_mb
        self._lock = Lock()

    def get_folder_size(self, folder):
        """Get total size of folder in MB"""
        total_size = 0
        for dirpath, _, filenames in os.walk(folder):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):  # Skip symlinks
                    total_size += os.path.getsize(fp)
        return total_size / (1024 * 1024)  # Convert to MB

    def cleanup_old_media(self):
        """Remove old media files if folder size exceeds limit"""
        with self._lock:
            try:
                current_size = self.get_folder_size(self.media_folder)
                if current_size > self.max_folder_size_mb:
                    log_info(f"Media folder size ({current_size:.2f}MB) exceeds limit ({self.max_folder_size_mb}MB)")
                    
                    # Get all subfolders with their creation times
                    folders = []
                    for item in os.listdir(self.media_folder):
                        item_path = os.path.join(self.media_folder, item)
                        if os.path.isdir(item_path):
                            ctime = os.path.getctime(item_path)
                            folders.append((item_path, ctime))
                    
                    # Sort by creation time (oldest first)
                    folders.sort(key=lambda x: x[1])
                    
                    # Remove oldest folders until we're under the limit
                    for folder_path, _ in folders:
                        if self.get_folder_size(self.media_folder) <= self.max_folder_size_mb:
                            break
                            
                        try:
                            import shutil
                            shutil.rmtree(folder_path)
                            log_success(f"Removed old media folder: {os.path.basename(folder_path)}")
                        except Exception as e:
                            log_error(f"Failed to remove folder {folder_path}: {e}")
                            
                        current_size = self.get_folder_size(self.media_folder)
                        if current_size <= self.max_folder_size_mb:
                            break
            except Exception as e:
                log_error(f"Error during media cleanup: {e}")

    def monitor_memory(self):
        """Monitor memory usage and cleanup if needed"""
        while True:
            self.cleanup_old_media()
            time.sleep(3600)  # Check every hour

# Create memory manager instance
memory_manager = MemoryManager(MEDIA_FOLDER)

# Start memory monitoring in a background thread
memory_thread = threading.Thread(target=memory_manager.monitor_memory, daemon=True)
memory_thread.start()
