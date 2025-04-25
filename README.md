# Instagram Auto Reposter

A Python application that automatically reposts saved Instagram content to your own account with proper attribution.

## Features

- Monitors your saved Instagram content (photos, videos, reels, IGTV, albums)
- Automatically reposts saved content to your account
- Likes original posts before reposting
- Customizable repost caption and check interval
- Credits original content creators in the caption
- Automatically removes posts from saved collection after reposting
- Option to keep downloaded media files

## Requirements

- Python 3.7+
- Instagram account with valid credentials
- Required Python packages:
  - instagrapi
  - colorama
  - python-dotenv
  - schedule
  - moviepy (for video processing)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/insta-bulk.git
   cd insta-bulk
   ```

2. Install required packages:
   ```
   pip install instagrapi colorama python-dotenv schedule moviepy==1.0.3
   ```

3. Create a `.env` file with your Instagram credentials:
   ```
   INSTAGRAM_USERNAME=your_username
   INSTAGRAM_PASSWORD=your_password
   REPOST_CAPTION="Reposted"
   CHECK_INTERVAL_MINUTES=30
   HISTORY_FILE=repost_history.json
   MEDIA_FOLDER=instagram_media
   KEEP_MEDIA=False
   ```

## Usage

Run the script:
```
python insta_reposter.py
```

The script will:
1. Log into your Instagram account (with cookie support for persistent sessions)
2. Check for saved posts at the interval specified in your .env file
3. Process each saved post (like, download, repost, unsave)
4. Keep track of reposted content to avoid duplicates

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `INSTAGRAM_USERNAME` | Your Instagram username | (Required) |
| `INSTAGRAM_PASSWORD` | Your Instagram password | (Required) |
| `REPOST_CAPTION` | Caption prefix for reposted content | "Reposted" |
| `CHECK_INTERVAL_MINUTES` | How often to check for new saved posts (in minutes) | 30 |
| `HISTORY_FILE` | File to store repost history | repost_history.json |
| `MEDIA_FOLDER` | Folder to temporarily store downloaded media | instagram_media |
| `COOKIES_FILE` | File to store Instagram session cookies | instagram_cookies.json |
| `KEEP_MEDIA` | Whether to keep downloaded media files (true/false) | False |

## How It Works

1. Save a post on Instagram
2. The script detects the saved content during its next check
3. The script likes the original post
4. The content is downloaded temporarily
5. The content is reposted to your profile with proper attribution
6. The post is removed from your saved collection
7. The post is added to history to avoid reposting

## Security and Error Handling

- Cookie-based authentication to maintain login sessions
- Comprehensive error handling and retry mechanisms
- Colorized console output for better debugging
- API connectivity checks to handle Instagram limitations

## Important Notes

- Instagram has rate limits. Setting a very short check interval may trigger account restrictions.
- Using automated tools with Instagram may violate their Terms of Service. Use at your own risk.
- For security, never share your .env file containing your credentials.
- The script works best when run continuously (e.g., on a server or cloud instance)

## Troubleshooting

If you encounter issues:
1. Check the console output for error messages
2. Ensure your Instagram credentials are correct
3. If you get login challenges, the script will prompt for verification codes
4. For persistent login issues, delete the cookies file and try again

## License

MIT 
