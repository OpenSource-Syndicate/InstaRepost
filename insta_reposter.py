import json
import os
import subprocess
import sys
import time

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
# Option to keep downloaded media files instead of deleting them
KEEP_MEDIA = os.getenv("KEEP_MEDIA", "False").lower() in ("true", "1", "yes")

# Create media folder if it doesn't exist
os.makedirs(MEDIA_FOLDER, exist_ok=True)

# Create Instagram client with better timeout settings
client = Client()
client.request_timeout = 30  # Increase default timeout to 30 seconds
client.logger.setLevel("INFO")  # Set logging level

saved_posts_history = set()

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
        # Try to import MoviePy
        try:
            import moviepy.editor

            MOVIEPY_AVAILABLE = True
            log_success("MoviePy successfully imported!")
        except ImportError:
            log_warning("MoviePy import failed. Installing specific version...")
            # Uninstall any existing version first to avoid conflicts
            subprocess.check_call(
                [sys.executable, "-m", "pip", "uninstall", "-y", "moviepy"]
            )
            # Install specific version that's known to work
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "moviepy==1.0.3"]
            )

            # Try importing again
            try:
                import moviepy.editor

                MOVIEPY_AVAILABLE = True
                log_success("MoviePy 1.0.3 installed and imported successfully!")
            except ImportError as e:
                log_error(f"MoviePy import still failed after installation: {e}")
                log_warning("You may need to restart the script after installation.")
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
    """Get user's saved posts using collection_medias_by_name."""
    try:
        log_info("Attempting to get saved posts from 'All Posts' collection")
        # 'All Posts' is the default collection for saved posts
        try:
            saved_posts = client.collection_medias_by_name("All Posts")
            log_success(
                f"Successfully fetched {len(saved_posts)} posts from 'All Posts' collection"
            )
            return saved_posts
        except Exception as e:
            log_warning(f"Failed to get posts from 'All Posts' collection: {e}")

        log_info("Attempting to get saved posts from 'Saved' collection")
        try:
            saved_posts = client.collection_medias_by_name("Saved")
            log_success(
                f"Successfully fetched {len(saved_posts)} posts from 'Saved' collection"
            )
            return saved_posts
        except Exception as e2:
            log_warning(f"Failed to get posts from 'Saved' collection: {e2}")

        log_info("Attempting to get all collections")
        try:
            collections = client.collections()
            log_info(f"Found {len(collections)} collections")

            if collections:
                first_collection = collections[0]
                log_info(
                    f"Attempting to fetch posts from collection: {first_collection.name} ({first_collection.id})"
                )
                saved_posts = client.collection_medias(first_collection.id)
                log_success(
                    f"Successfully fetched {len(saved_posts)} posts from collection: {first_collection.name}"
                )
                return saved_posts
            else:
                log_warning("No collections found")

                # Try getting saved posts directly using the new method
                log_info("Attempting to get all saved posts directly")
                try:
                    # Get the user's own ID first
                    user_id = client.user_id
                    # Use the new method to get saved posts
                    saved_posts = client.user_saved_medias(user_id)
                    log_success(
                        f"Successfully fetched {len(saved_posts)} posts using user_saved_medias()"
                    )
                    return saved_posts
                except Exception as e4:
                    log_error(f"Failed to get saved posts directly: {e4}")

                return []
        except Exception as e3:
            log_error(f"Failed to get collections: {e3}")

            # Try getting saved posts directly as a fallback
            log_info("Attempting to get all saved posts directly as fallback")
            try:
                # Get the user's own ID first
                user_id = client.user_id
                # Use the new method to get saved posts
                saved_posts = client.user_saved_medias(user_id)
                log_success(
                    f"Successfully fetched {len(saved_posts)} posts using user_saved_medias()"
                )
                return saved_posts
            except Exception as e4:
                log_error(f"Failed to get saved posts directly: {e4}")

            return []
    except Exception as e:
        log_error(f"Error in get_saved_posts: {e}")
        return []


def repost_media(media: Media):
    """Repost media based on its type."""
    try:
        media_id = media.id
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

        # Create folder for this media
        media_specific_folder = os.path.join(
            MEDIA_FOLDER, f"{media.user.username}_{media_id}"
        )
        os.makedirs(media_specific_folder, exist_ok=True)

        # Flag to track successful repost
        repost_successful = False

        # Handle different media types
        if media.media_type == 1:  # Photo
            log_info("Processing photo...")
            # Add retry logic for downloading
            max_retries = 3
            path = None
            for retry in range(max_retries):
                try:
                    # Use media folder for the download
                    path = client.photo_download(media_id, folder=media_specific_folder)
                    log_success(f"Downloaded photo: {media_id}")

                    # Immediately repost after downloading
                    log_info(f"Reposting photo: {media_id}")
                    client.photo_upload(path, caption)
                    log_success(f"Successfully uploaded photo: {media_id}")
                    repost_successful = True

                    # Immediately unsave after successful repost
                    if repost_successful:
                        try:
                            client.media_unsave(media_id)
                            log_success(f"Deleted post {media_id} from saved posts")
                        except Exception as unsave_error:
                            log_error(
                                f"Failed to delete post {media_id} from saved posts: {unsave_error}"
                            )

                    # Ensure the file is not in use before removing
                    if not KEEP_MEDIA and path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception as file_error:
                            log_warning(f"Could not remove file {path}: {file_error}")
                    else:
                        log_info(f"Keeping downloaded photo at: {path}")

                    break  # Exit retry loop if successful
                except Exception as e:
                    if retry < max_retries - 1:
                        log_warning(
                            f"Download/repost attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                        )
                        time.sleep(5)
                    else:
                        raise  # Re-raise if all retries fail

        elif media.media_type == 2:  # Video (including IGTV, Reels)
            if not MOVIEPY_AVAILABLE:
                log_warning("MoviePy is not available. Skipping video...")
                return

            log_info("Processing video...")
            path = None
            try:
                # Add retry logic for downloading
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        # Use media folder for the download
                        path = client.video_download(
                            media_id, folder=media_specific_folder
                        )
                        log_success(f"Downloaded video: {media_id}")
                        break  # Exit retry loop if successful
                    except Exception as e:
                        if retry < max_retries - 1:
                            log_warning(
                                f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                            )
                            time.sleep(5)
                        else:
                            raise  # Re-raise if all retries fail

                # Add short delay to ensure file is fully written
                time.sleep(2)

                # Immediately repost after successful download
                log_info(f"Reposting video: {media_id}")
                try:
                    if not media.product_type:  # Regular video
                        log_info(f"Uploading regular video: {media_id}")
                        client.video_upload(path, caption)
                        log_success(f"Successfully uploaded video: {media_id}")
                        repost_successful = True
                    elif media.product_type == "igtv":
                        log_info(f"Uploading IGTV: {media_id}")
                        client.igtv_upload(
                            path, caption, media.title or "Reposted IGTV"
                        )
                        log_success(f"Successfully uploaded IGTV: {media_id}")
                        repost_successful = True
                    elif media.product_type == "clips":  # Reels
                        log_info(f"Uploading Reel: {media_id}")
                        client.clip_upload(path, caption)
                        log_success(f"Successfully uploaded Reel: {media_id}")
                        repost_successful = True
                except Exception as upload_error:
                    log_error(f"Failed to upload video {media_id}: {upload_error}")
                    return

                # Immediately unsave after successful repost
                if repost_successful:
                    try:
                        client.media_unsave(media_id)
                        log_success(f"Deleted post {media_id} from saved posts")
                    except Exception as unsave_error:
                        log_error(
                            f"Failed to delete post {media_id} from saved posts: {unsave_error}"
                        )

                # Add delay before attempting to remove the file
                time.sleep(3)

                if KEEP_MEDIA and path:
                    log_info(f"Keeping downloaded video at: {path}")

            except Exception as e:
                log_error(f"Error processing video {media_id}: {e}")
                return
            finally:
                # Clean up file with retries if not keeping media
                if not KEEP_MEDIA and path and os.path.exists(path):
                    for retry in range(3):
                        try:
                            os.remove(path)
                            break
                        except Exception as file_error:
                            log_warning(
                                f"Attempt {retry + 1}: Could not remove video file: {file_error}"
                            )
                            time.sleep(2)  # Wait before retry

                # Check for thumbnail file and remove it if not keeping media
                thumbnail_path = f"{path}.jpg" if path else None
                if not KEEP_MEDIA and thumbnail_path and os.path.exists(thumbnail_path):
                    try:
                        os.remove(thumbnail_path)
                    except Exception as thumb_error:
                        log_warning(f"Could not remove thumbnail: {thumb_error}")

        elif media.media_type == 8:  # Album
            log_info("Processing album...")
            paths = []
            try:
                for i, resource in enumerate(media.resources):
                    # Add retry logic for downloading resources
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            # Create a subfolder for each resource to avoid name conflicts
                            resource_subfolder = os.path.join(
                                media_specific_folder, f"item_{i}"
                            )
                            os.makedirs(resource_subfolder, exist_ok=True)

                            if resource.media_type == 1:
                                # Use subfolder for the download to create unique filenames
                                resource_path = client.photo_download(
                                    resource.pk, folder=resource_subfolder
                                )
                                paths.append(resource_path)
                            elif resource.media_type == 2:
                                if not MOVIEPY_AVAILABLE:
                                    log_warning(
                                        "MoviePy is not available. Skipping video in album..."
                                    )
                                    continue
                                # Use subfolder for the download to create unique filenames
                                resource_path = client.video_download(
                                    resource.pk, folder=resource_subfolder
                                )
                                paths.append(resource_path)
                            break  # Exit retry loop if successful
                        except Exception as e:
                            if retry < max_retries - 1:
                                log_warning(
                                    f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                                )
                                time.sleep(5)
                            else:
                                log_error(
                                    f"Failed to download resource after {max_retries} attempts: {e}"
                                )

                log_success(
                    f"Successfully downloaded all album resources for {media_id}"
                )

                # Add short delay to ensure files are fully written
                time.sleep(2)

                # Immediately repost after all resources are downloaded
                if paths:  # Only upload if we have at least one valid media
                    log_info(f"Reposting album: {media_id}")
                    client.album_upload(paths, caption)
                    log_success(f"Successfully uploaded album: {media_id}")
                    repost_successful = True

                    # Immediately unsave after successful repost
                    if repost_successful:
                        try:
                            client.media_unsave(media_id)
                            log_success(f"Deleted post {media_id} from saved posts")
                        except Exception as unsave_error:
                            log_error(
                                f"Failed to delete post {media_id} from saved posts: {unsave_error}"
                            )

                    if KEEP_MEDIA:
                        log_info(
                            f"Keeping downloaded album media at: {media_specific_folder}"
                        )
                else:
                    log_warning("No valid media found in album")
            except Exception as e:
                log_error(f"Error processing album {media_id}: {e}")
                return
            finally:
                # Clean up downloaded files with retries if not keeping media
                if not KEEP_MEDIA:
                    for path in paths:
                        if os.path.exists(path):
                            for retry in range(3):
                                try:
                                    os.remove(path)
                                    break
                                except Exception as file_error:
                                    log_warning(
                                        f"Attempt {retry + 1}: Could not remove file {path}: {file_error}"
                                    )
                                    time.sleep(2)  # Wait before retry

                        # Check for thumbnail files and remove them
                        thumbnail_path = f"{path}.jpg"
                        if os.path.exists(thumbnail_path):
                            try:
                                os.remove(thumbnail_path)
                            except Exception as thumb_error:
                                log_warning(
                                    f"Could not remove thumbnail: {thumb_error}"
                                )

        # If repost was successful, add to history
        if repost_successful:
            # Add to history to avoid reposting
            saved_posts_history.add(media_id)

            # Save history after each successful repost
            save_history()

            log_success(f"Successfully reposted {media_id}")
        else:
            log_warning(
                f"Repost of {media_id} was not successful. Not adding to history."
            )
    except ImportError as e:
        log_error(f"Missing dependency error: {e}")
        log_warning(
            "Please install required packages and retry. Run: pip install moviepy==1.0.3"
        )
    except Exception as e:
        log_error(f"Error reposting media {media_id}: {e}")


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
    """Check for saved posts and repost them."""
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
        else:
            log_info(f"Processing {len(saved_medias)} saved posts")

            # Process each post one by one, immediately reposting after processing
            for i, media in enumerate(saved_medias):
                media_id = media.id
                log_info(f"Processing post {i + 1}/{len(saved_medias)}: {media_id}")

                # Skip if already reposted
                if media_id in saved_posts_history:
                    log_info(f"Skipping already reposted media: {media_id}")
                    continue

                # Process and repost this media
                log_info(f"Processing and reposting media: {media_id}")
                repost_media(media)

                # Short delay between processing posts to avoid rate limiting
                if i < len(saved_medias) - 1:  # No need to wait after the last post
                    time.sleep(5)

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
