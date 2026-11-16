"""Laptop -> Arduino LCD lyric bridge (Windows).

Reads the title, play/pause state and playback position from Windows' media
controls (the same thing behind the volume-flyout media widget), so it works
with YouTube in Chrome/Edge, Spotify, VLC, etc. Pause freezes the lyric,
resume continues from the same place, and seeking jumps to the right line.

Install:
  pip install pyserial requests unidecode
  pip install winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Storage.Streams
(older option, needs Python 3.12 or lower:  pip install winsdk)
"""
import asyncio
import time
from datetime import datetime, timezone

import requests
import serial

try:  # newer, prebuilt packages (work on Python 3.13/3.14)
  from winrt.windows.media.control import (
      GlobalSystemMediaTransportControlsSessionManager as MediaManager,
      GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlayStatus,
  )
except ImportError:  # older winsdk package
  from winsdk.windows.media.control import (
      GlobalSystemMediaTransportControlsSessionManager as MediaManager,
      GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlayStatus,
  )

from lyrics_utils import clean_title, current_index, parse_lrc, to_lcd_text, wrap_pages

# --- CONFIGURATION ---
PORT = "COM3"  # Keep your working port
BAUD = 9600
LYRIC_OFFSET = 0.0  # seconds; make positive if lyrics show too LATE, negative if too EARLY
POLL = 0.2

arduino = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

_last_payload = None


def send(line1, line2=""):
  """Send two 16-char lines to the Arduino (only when they change)."""
  global _last_payload
  payload = f"{line1[:16]}|{line2[:16]}\n"
  if payload != _last_payload:
    arduino.write(payload.encode("ascii", "ignore"))
    _last_payload = payload
    print(f"LCD: {line1!r} / {line2!r}")


# ------------------------------------------------------------------ lyrics
def _best(entries, duration):
  synced = [e for e in entries if e.get("syncedLyrics")]
  if not synced:
    return None
  if duration:
    synced.sort(key=lambda e: abs((e.get("duration") or 0) - duration))
  return synced[0]


def fetch_lyrics(title, artist, duration):
  """Return parsed synced lyrics [(sec, text)] or None. Blocking (run in thread)."""
  queries = []
  if artist:
    queries.append({"track_name": title, "artist_name": artist})
  queries.append({"q": f"{title} {artist}".strip()})
  queries.append({"q": title})
  for params in queries:
    try:
      r = requests.get("https://lrclib.net/api/search", params=params, timeout=8)
      entry = _best(r.json(), duration)
      if entry:
        print(f"Lyrics found: {entry.get('trackName')} - {entry.get('artistName')}")
        return parse_lrc(entry["syncedLyrics"])
    except Exception as exc:
      print(f"Lyric search failed: {exc}")
  return None


# ------------------------------------------------------------------ media state
async def read_media(manager):
  """Return dict(title, artist, playing, position, duration) or None."""
  session = manager.get_current_session()
  if session is None:
    return None
  props = await session.try_get_media_properties_async()
  info = session.get_playback_info()
  tl = session.get_timeline_properties()

  playing = info.playback_status == PlayStatus.PLAYING
  position = tl.position.total_seconds()
  duration = (tl.end_time - tl.start_time).total_seconds()
  # The OS stores the position at last_updated_time; add the time since then.
  if playing:
    age = (datetime.now(timezone.utc) - tl.last_updated_time).total_seconds()
    if 0 <= age < 3600:
      position += age
  return {
      "title": props.title or "",
      "artist": props.artist or "",
      "playing": playing,
      "position": position,
      "duration": duration,
  }


# ------------------------------------------------------------------ main loop
async def main():
  manager = await MediaManager.request_async()
  print("Lyric bridge active... play a song (YouTube / Spotify / VLC).")
  send("Ready for Lyrics", "Play a song")

  track_key = None
  lyrics = None
  fetching = None
  fallback_pos, fallback_t = 0.0, time.time()  # own clock if OS gives no position

  while True:
    try:
      media = await read_media(manager)
    except Exception as exc:
      print(f"Media read error: {exc}")
      await asyncio.sleep(1)
      continue

    if not media or not media["title"]:
      await asyncio.sleep(1)
      continue

    key = (media["title"], media["artist"])
    if key != track_key:  # new song
      track_key = key
      lyrics = None
      title = clean_title(media["title"], media["artist"])
      print(f"\nDetected: {title} | {media['artist']}")
      send("Searching...", to_lcd_text(title)[:16])
      fetching = asyncio.create_task(
          asyncio.to_thread(fetch_lyrics, title, media["artist"], media["duration"])
      )
      fallback_pos, fallback_t = 0.0, time.time()

    if fetching and fetching.done():
      lyrics = fetching.result()
      fetching = None
      if not lyrics:
        send("No synced lyrics", to_lcd_text(clean_title(media["title"]))[:16])

    # Position: OS value; if it is stuck at 0 (no timeline), use our own clock.
    now = time.time()
    if media["duration"] > 0:
      pos = media["position"]
    else:
      if media["playing"]:
        fallback_pos += now - fallback_t
      pos = fallback_pos
    fallback_t = now

    if lyrics:
      idx = current_index(lyrics, pos + LYRIC_OFFSET)
      if idx >= 0:
        ts, text = lyrics[idx]
        pages = wrap_pages(to_lcd_text(text))
        if len(pages) > 1:  # long line: step through pages during its duration
          nxt = lyrics[idx + 1][0] if idx + 1 < len(lyrics) else ts + 6
          frac = (pos + LYRIC_OFFSET - ts) / max(nxt - ts, 0.5)
          page = pages[min(int(max(frac, 0) * len(pages)), len(pages) - 1)]
        else:
          page = pages[0]
        send(*page)
      else:
        send("", "")

    await asyncio.sleep(POLL)


try:
  asyncio.run(main())
except KeyboardInterrupt:
  print("Exiting...")
  arduino.close()