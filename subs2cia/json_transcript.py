"""
Japanese sentence segmentation for ElevenLabs Scribe JSON transcripts.
Uses MeCab (via fugashi) for bunsetsu-based splitting to produce
one Anki card per sentence.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List


# POS1 categories that start a new bunsetsu
BUNSETSU_STARTERS = frozenset([
    "名詞",    # noun
    "動詞",    # verb
    "形容詞",  # i-adjective
    "形状詞",  # na-adjective
    "副詞",    # adverb
    "連体詞",  # pre-noun adjectival
    "接続詞",  # conjunction
    "感動詞",  # interjection
    "代名詞",  # pronoun
])

# Clause-ending patterns: the last morpheme in a bunsetsu signals a clause boundary.
CLAUSE_END_PARTICLES = frozenset([
    "て", "で",       # te-form
    "ば",             # conditional
    "から", "ので",   # reason
    "けど", "けれど", "けれども", "が",  # concessive
    "と", "たら", "なら",  # conditional
    "し",             # listing reasons
    "のに",           # despite
    "ながら",         # while
    "ても", "でも",   # even if
])

SENTENCE_ENDERS = frozenset("。！？!?")

MERGE_GAP_LIMIT = 0.4  # seconds — segments this far apart can never be merged into one cue
ANKI_COMMA_TOKEN_LIMIT = 5  # split at commas when cue has this many MeCab tokens or more


@dataclass
class CharToken:
    """A single character with its timestamp from ElevenLabs."""
    text: str
    start: float
    end: float
    speaker: str


@dataclass
class Bunsetsu:
    text: str
    start: float
    end: float
    speaker: str
    ends_clause: bool = False
    morph_count: int = 1

    def __repr__(self):
        return f"Bunsetsu({self.text!r}, {self.start:.2f}-{self.end:.2f}, {self.speaker}, clause={self.ends_clause})"


@dataclass
class Segment:
    """A maximally-split unit: one or more bunsetsu between hard boundaries."""
    bunsetsu: List[Bunsetsu]

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.bunsetsu)

    @property
    def start(self) -> float:
        return self.bunsetsu[0].start

    @property
    def end(self) -> float:
        return self.bunsetsu[-1].end

    @property
    def speaker(self) -> str:
        return self.bunsetsu[0].speaker

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.bunsetsu)


@dataclass
class Line:
    """A single subtitle line: one or more segments merged to fit a char limit."""
    segments: List[Segment]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)

    @property
    def start(self) -> float:
        return self.segments[0].start

    @property
    def end(self) -> float:
        return self.segments[-1].end

    @property
    def speaker(self) -> str:
        return self.segments[0].speaker

    @property
    def char_count(self) -> int:
        return sum(s.char_count for s in self.segments)


@dataclass
class Cue:
    """A subtitle cue: one or two lines displayed together."""
    lines: List[Line]

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    @property
    def start(self) -> float:
        return self.lines[0].start

    @property
    def end(self) -> float:
        return self.lines[-1].end

    @property
    def speaker(self) -> str:
        return self.lines[0].speaker

    @property
    def char_count(self) -> int:
        return sum(ln.char_count for ln in self.lines)

    @property
    def duration(self) -> float:
        return self.end - self.start


# ── JSON loading ──────────────────────────────────────────────────────────────

def load_chars(json_path: str, data: dict = None) -> List[CharToken]:
    """Load character tokens from ElevenLabs JSON, filtering non-word items.

    Multi-character tokens (e.g. '。API') are split into individual characters
    with linearly interpolated timestamps.
    """
    if data is None:
        with open(json_path) as f:
            data = json.load(f)

    chars = []
    for w in data["words"]:
        if w["type"] != "word":
            continue

        text = w["text"]
        start = w["start"]
        end = w["end"]
        speaker = w["speaker_id"]

        if len(text) == 1:
            chars.append(CharToken(text=text, start=start, end=end, speaker=speaker))
        else:
            # Split multi-char tokens, interpolate timing
            n = len(text)
            duration = end - start
            for i, ch in enumerate(text):
                ch_start = start + (duration * i / n)
                ch_end = start + (duration * (i + 1) / n)
                chars.append(CharToken(text=ch, start=ch_start, end=ch_end, speaker=speaker))

    return chars


# ── Speaker / sentence splitting ──────────────────────────────────────────────

def split_by_speaker(chars: List[CharToken]) -> List[List[CharToken]]:
    """Split character stream into runs of the same speaker."""
    if not chars:
        return []

    runs = []
    current_run = [chars[0]]

    for ch in chars[1:]:
        if ch.speaker != current_run[-1].speaker:
            runs.append(current_run)
            current_run = [ch]
        else:
            current_run.append(ch)

    runs.append(current_run)
    return runs


def split_by_sentence(chars: List[CharToken]) -> List[List[CharToken]]:
    """Split a character run on sentence-ending punctuation.

    The punctuation character stays with the sentence it ends (attached left).
    """
    if not chars:
        return []

    sentences = []
    current: List[CharToken] = []

    for ch in chars:
        current.append(ch)
        if ch.text in SENTENCE_ENDERS:
            sentences.append(current)
            current = []

    if current:
        sentences.append(current)

    return sentences


# ── Bunsetsu segmentation ────────────────────────────────────────────────────

def chars_to_bunsetsu(chars: List[CharToken], tagger) -> List[Bunsetsu]:
    """
    Concatenate chars into text, run MeCab, then group morphemes into
    bunsetsu while mapping back to character-level timestamps.
    """
    if not chars:
        return []

    text = "".join(ch.text for ch in chars)
    speaker = chars[0].speaker

    morphemes = tagger(text)

    char_offset = 0
    bunsetsu_list: List[Bunsetsu] = []
    current_chars: List[CharToken] = []
    current_morphs: list = []
    prefix_active = False

    def flush():
        if current_chars:
            bunsetsu_list.append(_make_bunsetsu(current_chars, current_morphs, speaker))

    for morph in morphemes:
        surface = morph.surface
        pos1 = morph.feature.pos1
        pos2 = morph.feature.pos2 or ""

        morph_len = len(surface)
        morph_chars = chars[char_offset:char_offset + morph_len]
        char_offset += morph_len

        is_starter = pos1 in BUNSETSU_STARTERS
        is_prefix = pos1 == "接頭辞"

        if is_prefix:
            flush()
            current_chars = list(morph_chars)
            current_morphs = [(surface, pos1, pos2)]
            prefix_active = True

        elif is_starter:
            if prefix_active:
                current_chars.extend(morph_chars)
                current_morphs.append((surface, pos1, pos2))
                prefix_active = False
            else:
                flush()
                current_chars = list(morph_chars)
                current_morphs = [(surface, pos1, pos2)]

        else:
            if not current_chars:
                current_chars = list(morph_chars)
                current_morphs = [(surface, pos1, pos2)]
            else:
                current_chars.extend(morph_chars)
                current_morphs.append((surface, pos1, pos2))
            prefix_active = False

    flush()
    return bunsetsu_list


def _make_bunsetsu(chars: List[CharToken], morphs: list, speaker: str) -> Bunsetsu:
    text = "".join(ch.text for ch in chars)

    ends_clause = False
    if morphs:
        last_surface, last_pos1, last_pos2 = morphs[-1]
        if last_pos1 == "助動詞":
            ends_clause = True
        elif last_pos1 == "助詞" and last_surface in CLAUSE_END_PARTICLES:
            ends_clause = True
        if len(morphs) >= 2 and last_pos1 in ("補助記号", "記号"):
            prev_surface, prev_pos1, prev_pos2 = morphs[-2]
            if prev_pos1 == "助動詞":
                ends_clause = True
            elif prev_pos1 == "助詞" and prev_surface in CLAUSE_END_PARTICLES:
                ends_clause = True

    return Bunsetsu(
        text=text,
        start=chars[0].start,
        end=chars[-1].end,
        speaker=speaker,
        ends_clause=ends_clause,
        morph_count=len(morphs),
    )


# ── Bunsetsu loading (JSON → all_bunsetsu) ───────────────────────────────────

def _load_bunsetsu(json_path: str, data: dict = None) -> List[Bunsetsu]:
    """Load an ElevenLabs JSON file and return all bunsetsu."""
    from fugashi import Tagger

    chars = load_chars(json_path, data=data)
    speaker_runs = split_by_speaker(chars)

    tagger = Tagger()
    all_bunsetsu: List[Bunsetsu] = []

    for run in speaker_runs:
        sentences = split_by_sentence(run)
        for sentence_chars in sentences:
            bunsetsu = chars_to_bunsetsu(sentence_chars, tagger)
            all_bunsetsu.extend(bunsetsu)

    return all_bunsetsu


# ── Anki cue builder ─────────────────────────────────────────────────────────

def bunsetsu_to_anki_cues(bunsetsu_list: List[Bunsetsu]) -> List[Cue]:
    """Build cues for Anki: one sentence per cue, split on 。！？ and speaker changes.

    Long cues get split into two balanced lines at a bunsetsu boundary.
    """
    if not bunsetsu_list:
        return []

    cues: List[Cue] = []
    current: List[Bunsetsu] = []

    def flush():
        if not current:
            return
        line = Line(segments=[Segment(bunsetsu=list(current))])
        cues.append(Cue(lines=[line]))
        current.clear()

    def next_section_token_count(idx: int) -> int:
        """Count MeCab tokens in the section following bunsetsu_list[idx],
        up to the next comma, period, or end of sentence."""
        count = 0
        for b2 in bunsetsu_list[idx + 1:]:
            if b2.speaker != bunsetsu_list[idx].speaker:
                break
            count += b2.morph_count
            if b2.text and b2.text[-1] in SENTENCE_ENDERS or b2.text[-1] == "、":
                break
        return count

    for i, b in enumerate(bunsetsu_list):
        if current and b.speaker != current[-1].speaker:
            flush()

        if current and b.start - current[-1].end >= MERGE_GAP_LIMIT:
            flush()

        current.append(b)

        if b.text and b.text[-1] in SENTENCE_ENDERS:
            flush()
        elif b.text and b.text[-1] == "、":
            token_count = sum(bu.morph_count for bu in current)
            if token_count >= ANKI_COMMA_TOKEN_LIMIT:
                next_tokens = next_section_token_count(i)
                if not (next_tokens <= 2 and token_count <= 7):
                    flush()

    flush()
    return cues


# ── Top-level entry point ────────────────────────────────────────────────────

def load_json_cues(json_path: Path) -> List[Cue]:
    """Load a Scribe JSON transcript and return sentence-level cues.

    Validates that the transcript is Japanese and that fugashi is installed.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    lang = data.get('language_code', '')
    if lang not in ('jpn', 'ja'):
        raise ValueError(
            f"JSON transcript language is '{lang}', but srs export from JSON "
            f"is only supported for Japanese (jpn) transcripts."
        )

    try:
        import fugashi  # noqa: F401
    except ImportError:
        raise ImportError(
            "fugashi is required for Japanese JSON transcript processing. "
            "Install it with: pip install fugashi[unidic-lite]"
        )

    logging.info(f"Loading Japanese JSON transcript for srs export: {json_path}")
    all_bunsetsu = _load_bunsetsu(str(json_path), data=data)
    cues = bunsetsu_to_anki_cues(all_bunsetsu)
    logging.info(f"Created {len(cues)} sentence cues from JSON transcript")

    return cues
