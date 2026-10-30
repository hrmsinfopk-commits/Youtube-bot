"""Copies stdin to stdout and a log file, hiding any secret values (log is committed to the repo)."""
import os
import sys

NAMES = ["GEMINI_API_KEY", "LYRIA_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY",
         "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]
secrets = [os.environ.get(n, "") for n in NAMES]
secrets = [s for s in secrets if len(s) >= 6]

with open(sys.argv[1], "w", encoding="utf-8") as log:
    for line in sys.stdin:
        for s in secrets:
            line = line.replace(s, "***")
        sys.stdout.write(line)
        sys.stdout.flush()
        log.write(line)
        log.flush()
