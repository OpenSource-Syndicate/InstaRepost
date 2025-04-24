import json
import os
import subprocess
import sys
import time

import schedule
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.types import Media

# Load environment variables
load_dotenv()
USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
REPOST_CAPTION = os.getenv("REPOST_CAPTION", "Reposted")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", 30))
HISTORY_FILE = os.getenv("HISTORY_FILE", "repost_history.json")
MEDIA_FOLDER = os.getenv("MEDIA_FOLDER", "instagram_media")
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


def check_dependencies():
    """Check and install required dependencies."""
    global MOVIEPY_AVAILABLE
    try:
        # Try to import MoviePy
        try:
            import moviepy.editor

            MOVIEPY_AVAILABLE = True
            print("MoviePy successfully imported!")
        except ImportError:
            print("MoviePy import failed. Installing specific version...")
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
                print("MoviePy 1.0.3 installed and imported successfully!")
            except ImportError as e:
                print(f"MoviePy import still failed after installation: {e}")
                print("You may need to restart the script after installation.")
                return False

        print("All dependencies verified!")
        return True
    except Exception as e:
        print(f"Error checking/installing dependencies: {e}")
        print("Please manually install required dependencies with:")
        print("pip install moviepy==1.0.3")
        return False


def load_history():
    """Load repost history from JSON file."""
    global saved_posts_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                saved_posts_history = set(json.load(f))
            print(f"Loaded {len(saved_posts_history)} posts from history file.")
        else:
            saved_posts_history = set()
    except Exception as e:
        print(f"Error loading history file: {e}")
        saved_posts_history = set()


def save_history():
    """Save repost history to JSON file."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(saved_posts_history), f)
        print(f"Saved {len(saved_posts_history)} posts to history file.")
    except Exception as e:
        print(f"Error saving history file: {e}")


def login():
    """Login to Instagram account."""
    try:
        print(f"Logging in as {USERNAME}...")
        client.login(USERNAME, PASSWORD)
        print("Login successful!")
        return True
    except Exception as e:
        print(f"Login failed: {e}")
        return False


def get_saved_posts():
    """Get user's saved posts using collection_medias_by_name."""
    try:
        # 'All Posts' is the default collection for saved posts
        return client.collection_medias_by_name("All Posts")
    except Exception as e:
        try:
            # Some accounts might have saved posts in "Saved" collection
            return client.collection_medias_by_name("Saved")
        except Exception as e2:
            try:
                # Try to get all collections and fetch from the first one
                collections = client.collections()
                if collections:
                    first_collection = collections[0]
                    return client.collection_medias(first_collection.id)
                else:
                    print(f"No collections found: {e2}")
                    return []
            except Exception as e3:
                print(f"Error getting saved posts: {e}, {e2}, {e3}")
                return []


def repost_media(media: Media):
    """Repost media based on its type."""
    try:
        media_id = media.id
        if media_id in saved_posts_history:
            print(f"Skipping already reposted media: {media_id}")
            return

        print(f"Reposting media: {media_id}")
        caption = f"{REPOST_CAPTION}\n\nOriginal by @{media.user.username}"

        # Create folder for this media
        media_specific_folder = os.path.join(
            MEDIA_FOLDER, f"{media.user.username}_{media_id}"
        )
        os.makedirs(media_specific_folder, exist_ok=True)

        # Handle different media types
        if media.media_type == 1:  # Photo
            print("Processing photo...")
            # Add retry logic for downloading
            max_retries = 3
            for retry in range(max_retries):
                try:
                    # Use media folder for the download
                    path = client.photo_download(media_id, folder=media_specific_folder)
                    client.photo_upload(path, caption)

                    # Ensure the file is not in use before removing
                    if not KEEP_MEDIA:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except Exception as file_error:
                            print(
                                f"Warning: Could not remove file {path}: {file_error}"
                            )
                    else:
                        print(f"Keeping downloaded photo at: {path}")

                    break  # Exit retry loop if successful
                except Exception as e:
                    if retry < max_retries - 1:
                        print(
                            f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                        )
                        time.sleep(5)
                    else:
                        raise  # Re-raise if all retries fail

        elif media.media_type == 2:  # Video (including IGTV, Reels)
            if not MOVIEPY_AVAILABLE:
                print("MoviePy is not available. Skipping video...")
                return

            print("Processing video...")
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
                        break  # Exit retry loop if successful
                    except Exception as e:
                        if retry < max_retries - 1:
                            print(
                                f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                            )
                            time.sleep(5)
                        else:
                            raise  # Re-raise if all retries fail

                # Add short delay to ensure file is fully written
                time.sleep(2)

                if not media.product_type:  # Regular video
                    client.video_upload(path, caption)
                elif media.product_type == "igtv":
                    client.igtv_upload(path, caption, media.title or "Reposted IGTV")
                elif media.product_type == "clips":  # Reels
                    client.clip_upload(path, caption)

                # Add delay before attempting to remove the file
                time.sleep(3)

                if KEEP_MEDIA and path:
                    print(f"Keeping downloaded video at: {path}")

            except Exception as e:
                print(f"Error processing video {media_id}: {e}")
                return
            finally:
                # Clean up file with retries if not keeping media
                if not KEEP_MEDIA and path and os.path.exists(path):
                    for retry in range(3):
                        try:
                            os.remove(path)
                            break
                        except Exception as file_error:
                            print(
                                f"Attempt {retry + 1}: Could not remove video file: {file_error}"
                            )
                            time.sleep(2)  # Wait before retry

                # Check for thumbnail file and remove it if not keeping media
                thumbnail_path = f"{path}.jpg" if path else None
                if not KEEP_MEDIA and thumbnail_path and os.path.exists(thumbnail_path):
                    try:
                        os.remove(thumbnail_path)
                    except Exception as thumb_error:
                        print(f"Could not remove thumbnail: {thumb_error}")

        elif media.media_type == 8:  # Album
            print("Processing album...")
            paths = []
            try:
                for i, resource in enumerate(media.resources):
                    # Add retry logic for downloading resources
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            if resource.media_type == 1:
                                # Use media folder for the download with index to avoid name conflicts
                                resource_path = client.photo_download(
                                    resource.pk,
                                    folder=media_specific_folder,
                                    filename=f"item_{i}",
                                )
                                paths.append(resource_path)
                            elif resource.media_type == 2:
                                if not MOVIEPY_AVAILABLE:
                                    print(
                                        "MoviePy is not available. Skipping video in album..."
                                    )
                                    continue
                                # Use media folder for the download with index to avoid name conflicts
                                resource_path = client.video_download(
                                    resource.pk,
                                    folder=media_specific_folder,
                                    filename=f"item_{i}",
                                )
                                paths.append(resource_path)
                            break  # Exit retry loop if successful
                        except Exception as e:
                            if retry < max_retries - 1:
                                print(
                                    f"Download attempt {retry + 1} failed: {e}. Retrying in 5 seconds..."
                                )
                                time.sleep(5)
                            else:
                                print(
                                    f"Failed to download resource after {max_retries} attempts: {e}"
                                )

                # Add short delay to ensure files are fully written
                time.sleep(2)

                if paths:  # Only upload if we have at least one valid media
                    client.album_upload(paths, caption)
                    if KEEP_MEDIA:
                        print(
                            f"Keeping downloaded album media at: {media_specific_folder}"
                        )
                else:
                    print("No valid media found in album")
            except Exception as e:
                print(f"Error processing album {media_id}: {e}")
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
                                    print(
                                        f"Attempt {retry + 1}: Could not remove file {path}: {file_error}"
                                    )
                                    time.sleep(2)  # Wait before retry

                        # Check for thumbnail files and remove them
                        thumbnail_path = f"{path}.jpg"
                        if os.path.exists(thumbnail_path):
                            try:
                                os.remove(thumbnail_path)
                            except Exception as thumb_error:
                                print(f"Could not remove thumbnail: {thumb_error}")

        # Add to history to avoid reposting
        saved_posts_history.add(media_id)

        # Save history after each successful repost
        save_history()

        print(f"Successfully reposted {media_id}")
    except ImportError as e:
        print(f"Missing dependency error: {e}")
        print(
            "Please install required packages and retry. Run: pip install moviepy==1.0.3"
        )
    except Exception as e:
        print(f"Error reposting media {media_id}: {e}")


def check_and_repost():
    """Check for saved posts and repost them."""
    if not client.user_id:
        if not login():
            return

    print("Checking for saved posts to repost...")
    saved_medias = get_saved_posts()

    for media in saved_medias:
        repost_media(media)

    print(f"Completed check. Next check in {CHECK_INTERVAL} minutes.")


def main():
    """Main function to run the reposter."""
    if not USERNAME or not PASSWORD:
        print("Instagram credentials not found or invalid!")
        print("Please create a .env file with the following content:")
        print("INSTAGRAM_USERNAME=your_username")
        print("INSTAGRAM_PASSWORD=your_password")
        print('REPOST_CAPTION="Reposted"')
        print("CHECK_INTERVAL_MINUTES=30")
        print("HISTORY_FILE=repost_history.json")
        print("MEDIA_FOLDER=instagram_media")
        print("KEEP_MEDIA=False  # Set to True to keep downloaded media files")
        print("\nOr provide these values as environment variables.")
        return

    try:
        # Check and install dependencies
        if not check_dependencies():
            print(
                "Required dependencies are missing. Please install them and try again."
            )
            return

        # Test if the Client initialization works properly
        print("Testing Instagram client initialization...")
        if not login():
            print(
                "Instagram client initialization failed. Please check your credentials and try again."
            )
            return

        # Load history from file
        load_history()

        print(f"Setting up scheduler to check every {CHECK_INTERVAL} minutes.")

        # Schedule the check
        schedule.every(CHECK_INTERVAL).minutes.do(check_and_repost)

        # Run immediately for the first time
        check_and_repost()

        # Keep the script running
        print("Instagram Auto Reposter is now running! Press Ctrl+C to stop.")
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Instagram Auto Reposter...")
        save_history()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        save_history()


if __name__ == "__main__":
    main()
