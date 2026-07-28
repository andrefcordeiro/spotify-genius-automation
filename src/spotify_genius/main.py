import sys
import time
from pathlib import Path

# Make `python src/spotify_genius/main.py` import this checkout instead of any
# previously installed spotify_genius package.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spotify_genius.platforms import get_current_song
from spotify_genius.core import genius_window_closed, open_genius

def run():
    print('Waiting for tracks...')
    previous = None

    while True:
        if genius_window_closed():
            print("Genius window closed. Exiting.")
            return

        artist, title = get_current_song()

        if not artist or not title:
            time.sleep(2)
            continue

        current = (artist, title)

        if current != previous:
            previous = current
            print(f'\nNow playing: {artist} - {title}')

            open_genius(artist, title)

        time.sleep(2)

if __name__ == "__main__":
    run()
