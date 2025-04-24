# Instagram Auto Reposter

A Python application that monitors your saved Instagram posts and automatically reposts them to your account.

## Features

- Monitors your saved Instagram content (photos, videos, reels, IGTV, albums)
- Automatically reposts saved content to your account
- Customizable repost caption and check interval
- Credits original content creators in the caption

## Requirements

- Python 3.7+
- Instagram account with valid credentials
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/insta-bulk.git
   cd insta-bulk
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your Instagram credentials:
   ```
   INSTAGRAM_USERNAME=your_username
   INSTAGRAM_PASSWORD=your_password
   REPOST_CAPTION="Reposted"
   CHECK_INTERVAL_MINUTES=30
   ```

## Usage

Run the script:
```
python insta_reposter.py
```

The script will:
1. Log into your Instagram account
2. Record existing saved posts (won't repost these)
3. Check for new saved posts at the interval specified in your .env file
4. Automatically repost any new saved content

## How It Works

1. Save a post or reel on Instagram
2. The script detects the newly saved content during its next check
3. The content is downloaded temporarily
4. The content is reposted to your profile with proper attribution
5. The saved post is added to history to avoid reposting

## Important Notes

- Instagram has rate limits. Setting a very short check interval may trigger account restrictions.
- Using automated tools with Instagram may violate their Terms of Service. Use at your own risk.
- For security, never share your .env file containing your credentials.

## Customization

Edit the `.env` file to customize:
- `REPOST_CAPTION`: The caption prefix for reposted content
- `CHECK_INTERVAL_MINUTES`: How often to check for new saved posts (in minutes)

## License

MIT 