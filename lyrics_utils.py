"""Helpers for lyric_maker.py: LRC parsing, LCD-safe text conversion, wrapping."""
import re

try:
  from unidecode import unidecode
except ImportError:  # works without it, but non-Tamil scripts will be dropped
  unidecode = None


# ---------------------------------------------------------------- Tamil -> ASCII
# The 16x2 LCD (HD44780) has no Tamil glyphs, so Tamil is shown as readable
# English letters ("Tanglish"), e.g. வணக்கம் -> vanakkam.
#
# The converter follows Tamil pronunciation rules (not a letter-by-letter map):
#   * all 12 vowels, 18 consonants, aytham (ஃ), grantha letters (ஜ ஷ ஸ ஹ க்ஷ ஸ்ரீ)
#   * the 5 stops க ச ட த ப sound different by position:
#       word start .......... k   s   t   th  p
#       between vowels ...... g   s   d   dh  b      (அகம் agam, அடி adi, பசு pasu)
#       after a nasal ....... g   j   d   dh  b      (ங்க ng, ஞ்ச nj, ண்ட nd, ந்த ndh, ம்ப mb)
#       doubled ............. kk  cch tt  th  pp     (பக்கம் pakkam, இச்சை icchai)
#   * special clusters: ற்ற tr, ன்ற ndr, க்ஷ ksh, ஞ initial gn, ஃப f
#   * Tamil digits, zero-width joiners and split vowel signs (ெ+ா = ொ) are cleaned up

_T_VOWELS = {
    "அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ee", "உ": "u", "ஊ": "oo",
    "எ": "e", "ஏ": "e", "ஐ": "ai", "ஒ": "o", "ஓ": "o", "ஔ": "au",
}
_T_CONS = {
    "க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "t", "ண": "n",
    "த": "th", "ந": "n", "ப": "p", "ம": "m", "ய": "y", "ர": "r",
    "ல": "l", "வ": "v", "ழ": "zh", "ள": "l", "ற": "r", "ன": "n",
    "ஜ": "j", "ஷ": "sh", "ஸ": "s", "ஹ": "h", "ஶ": "sh",
}
_T_SIGNS = {
    "ா": "aa", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e",
    "ே": "e", "ை": "ai", "ொ": "o", "ோ": "o", "ௌ": "au", "ௗ": "au",
}
_PULLI = "்"
_AYTHAM = "ஃ"

# (word start, between vowels / after sonorant or nasal, doubled)
_STOPS = {
    "க": ("k", "g"), "ச": ("s", "s"), "ட": ("t", "d"),
    "த": ("th", "dh"), "ப": ("p", "b"),
}
_NASALS = set("ஙஞணநமன")
_SONORANTS = set("யரலவழள")

_TAMIL_RUN = re.compile("[஀-௿‌‍]+")
_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

# Letter sequences that must be fixed before parsing.
_NORMALISE = [
    ("‌", ""), ("‍", ""),
    ("ொ", "ொ"), ("ோ", "ோ"), ("ௌ", "ௌ"),  # split vowel signs -> single sign
    ("ஸ்ரீ", "ஸ்ரீ"), ("ஶ்ரீ", "ஸ்ரீ"),
]
_SPECIAL_WORDS = {"ஸ்ரீ": "sri", "ஓம்": "om"}

# Words whose usual spelling differs from the rules. Keys are word STARTS
# (stems), so suffixes still work: சந்திரனோ -> chandhirano.
# Add your own here whenever a word looks wrong on the LCD.
CUSTOM_STEMS = {
    "சந்திர": "chandhira",
    "சென்னை": "chennai",
    "சின்ன": "chinna",
    "சிங்கம்": "singam",
    "ஞாயிறு": "gnaayiru",
    "ஞானம்": "gnaanam",
    "ஞாபக": "gnaabaga",
    "என்": "en",
    "உன்": "un",
}
_STEM_ORDER = sorted(CUSTOM_STEMS, key=len, reverse=True)


def _parse_word(word):
  """Split a Tamil word into units: ('v', text) or ('c', letter, vowel, dead)."""
  units = []
  i, n = 0, len(word)
  while i < n:
    ch = word[i]
    if ch in _T_CONS:
      letter = ch
      i += 1
      if letter == "க" and word[i:i + 2] == _PULLI + "ஷ":  # க்ஷ conjunct
        letter = "X"
        i += 2
      vowel, dead = "a", False
      if i < n and word[i] == _PULLI:
        vowel, dead = "", True
        i += 1
      elif i < n and word[i] in _T_SIGNS:
        vowel = _T_SIGNS[word[i]]
        i += 1
      units.append(("c", letter, vowel, dead))
    elif ch in _T_VOWELS:
      units.append(("v", _T_VOWELS[ch]))
      i += 1
    elif ch == _AYTHAM:
      units.append(("a",))
      i += 1
    else:  # stray sign / symbol
      units.append(("v", ""))
      i += 1
  return units


def _is_cons(unit, letter=None):
  return unit is not None and unit[0] == "c" and (letter is None or unit[1] == letter)


def _convert_units(units):
  out = []
  for idx, u in enumerate(units):
    if u[0] == "v":
      out.append(u[1])
      continue
    if u[0] == "a":  # aytham: ஃப -> f, otherwise a soft h
      nxt = units[idx + 1] if idx + 1 < len(units) else None
      out.append("" if _is_cons(nxt, "ப") else "h")
      continue

    _, letter, vowel, dead = u
    prev = units[idx - 1] if idx > 0 else None
    nxt = units[idx + 1] if idx + 1 < len(units) else None
    prev_dead = _is_cons(prev) and prev[3]
    prev_letter = prev[1] if prev_dead else None
    vowel_before = prev is not None and (prev[0] == "v" or (prev[0] == "c" and not prev[3]))
    after_aytham = prev is not None and prev[0] == "a"

    if after_aytham and letter == "ப":
      s = "f"
    elif letter == "X":
      s = "ksh"
    elif letter in _STOPS:
      voiceless, voiced = _STOPS[letter]
      if dead:  # a stop with a pulli: kk, tt, pp, cch, kt ...
        if letter == "த" and _is_cons(nxt, "த"):
          s = ""  # த்த -> single "th" (ரத்தினம் -> rathinam)
        elif letter == "ச" and _is_cons(nxt, "ச"):
          s = "c"  # ச்ச -> "cch"
        else:
          s = voiceless
      elif prev is None:
        s = voiceless
      elif prev_letter == letter:  # second half of a double: kk, tt, pp, cch
        s = "ch" if letter == "ச" else voiceless
      elif vowel_before or after_aytham:
        s = voiced
      elif prev_letter == "ஞ" and letter == "ச":
        s = "j"  # ஞ்ச -> nj
      elif prev_letter in _NASALS or prev_letter in _SONORANTS:
        s = voiced if letter != "ச" else "s"
      else:
        s = voiceless
    elif letter == "ற":
      if dead and _is_cons(nxt, "ற"):
        s = "t"  # ற்ற -> tr
      elif prev_letter == "ன":
        s = "dr"  # ன்ற -> ndr
      else:
        s = "r"
    elif letter == "ங":
      if dead:
        s = "n" if _is_cons(nxt, "க") else "ng"
      else:
        s = "ng"
    elif letter == "ஞ":
      if prev is None and not dead:
        s = "gn"  # ஞானம் -> gnaanam
      elif dead:
        s = "n" if _is_cons(nxt, "ச") else "nj"
      else:
        s = "nj"
    else:
      s = _T_CONS[letter]
    out.append(s + vowel)
  return "".join(out)


def _convert_word(word):
  if word in _SPECIAL_WORDS:
    return _SPECIAL_WORDS[word]
  for stem in _STEM_ORDER:
    if word.startswith(stem):
      return CUSTOM_STEMS[stem] + _convert_units(_parse_word(word[len(stem):]))
  return _convert_units(_parse_word(word))


def _tamil_to_ascii(text):
  text = text.translate(_DIGITS)
  for a, b in _NORMALISE:
    text = text.replace(a, b)
  return _TAMIL_RUN.sub(lambda m: _convert_word(m.group(0)), text)


def to_lcd_text(text):
  """Convert any lyric line into plain ASCII the LCD can display."""
  text = _tamil_to_ascii(text)
  if unidecode:
    text = unidecode(text)  # Hindi, Telugu, Malayalam, Korean, Japanese, ...
  text = re.sub(r"[^\x20-\x7e]", "", text)
  return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- LRC parsing
_LRC = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(synced):
  """'[01:23.45] text' lines -> sorted [(seconds, text)]; blanks are kept."""
  lines = []
  for raw in synced.splitlines():
    stamps = _LRC.findall(raw)
    if not stamps:
      continue
    text = _LRC.sub("", raw).strip()
    for m, s in stamps:
      lines.append((int(m) * 60 + float(s), text))
  lines.sort(key=lambda x: x[0])
  return lines


def current_index(lyrics, position):
  """Index of the line active at `position` seconds, or -1 before the first."""
  lo, hi, idx = 0, len(lyrics) - 1, -1
  while lo <= hi:
    mid = (lo + hi) // 2
    if lyrics[mid][0] <= position:
      idx, lo = mid, mid + 1
    else:
      hi = mid - 1
  return idx


# ---------------------------------------------------------------- Title cleaning
_NOISE = re.compile(
    r"[\(\[](official|lyric|lyrics|video|audio|full|hd|4k|song|music|"
    r"video song|lyrical|remastered|ft\.?|feat\.?)[^\)\]]*[\)\]]",
    re.I,
)


def clean_title(title, artist=""):
  """Strip YouTube noise so the lyric search matches."""
  t = _NOISE.sub("", title or "")
  t = re.sub(r"\s*\|.*$", "", t)  # "Song | Movie | Artist" -> "Song"
  t = re.sub(r"\s*-\s*YouTube.*$", "", t, flags=re.I)
  t = re.sub(r"\s+", " ", t).strip(" -")
  return t


# ---------------------------------------------------------------- 16x2 wrapping
def wrap_pages(text, width=16, rows=2):
  """Split text into word-wrapped pages of `rows` lines x `width` chars."""
  words = text.split()
  lines, cur = [], ""
  for w in words:
    while len(w) > width:  # very long word
      if cur:
        lines.append(cur)
        cur = ""
      lines.append(w[:width])
      w = w[width:]
    if not cur:
      cur = w
    elif len(cur) + 1 + len(w) <= width:
      cur += " " + w
    else:
      lines.append(cur)
      cur = w
  if cur:
    lines.append(cur)
  if not lines:
    return [("", "")]
  pages = []
  for i in range(0, len(lines), rows):
    chunk = lines[i:i + rows]
    chunk += [""] * (rows - len(chunk))
    pages.append(tuple(chunk))
  return pages
