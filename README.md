# subs2cia

Extract subtitled dialogue from video and audio files for language learning. Generates condensed listening tracks, SRS flashcard exports (with audio clips, screenshots, and context), and more.

## Features

### Condense (`subs2cia condense`)

Create condensed audio/video that contains only the spoken dialogue, cutting out all silence.

- Simultaneous and overlapping subtitle lines are merged for seamless listening
- Automatically generates condensed subtitles, audio, and video (video requires `-m`)
- Auto-selects subtitle and audio tracks by language, or manually specify streams (`-tl`, `-si`, `-ai`, `-ls`)
- Filters out non-dialogue lines (signs, songs, sound effects) using built-in heuristics or custom regexes (`-ni`, `-R`)
- Ignore openings/endings by time range (`-I`) or by chapter (`-Ic`)
- Reinserts natural spacing between closely-timed sentences (`-t`)
- Pads subtitles with extra audio for better context (`-p`)
- Partition and split long outputs into manageable chunks (`-r`, `-s`)
- Batch mode for processing entire series at once (`-b`)
- **JSON transcript input** — use transcribed JSON files (e.g. from ElevenLabs Scribe) instead of subtitle files

### SRS Export (`subs2cia srs`)

Export every subtitle line as a separate flashcard with audio, screenshot, and surrounding context for import into Anki or other SRS applications.

- Outputs a TSV file with audio clips, screenshots, and sentence context
- Optional video clip export (`--export-video`)
- Normalize audio volume across clips (`-N`)
- Direct export to Anki media folder (`--media-dir`)
- Toggle audio/screenshot export (`--no-export-audio`, `--no-export-screenshot`)
- Context column with surrounding lines for LLM-assisted study
- **JSON transcript input** — use transcribed JSON files for Japanese sentence-level card generation with MeCab-based segmentation

### subzipper

Renames subtitle files to match video files for Plex-style naming conventions.

## Requirements

- **Python** 3.6 or later
- **ffmpeg** — `ffmpeg` and `ffprobe` must be on your PATH
- **pip packages** (installed automatically): ffmpeg-python, pycountry, pysubs2, tqdm, gevent, colorlog

### Optional dependencies

- **fugashi** — Required only for JSON transcript → SRS card generation (Japanese). Install with:
  ```
  pip install fugashi[unidic-lite]
  ```
  Not needed for condensed audio from JSON, or for any subtitle-based workflows.

## Installation

### pip (from PyPI)

```
pip install subs2cia
```

### pipx (recommended for CLI tools)

```
pipx install subs2cia
```

### From source

```
git clone https://github.com/mattvsjapan/subs2cia
cd subs2cia
pip install .
```

### Platform notes

**macOS** — Install Python and ffmpeg via [Homebrew](https://brew.sh/):
```
brew install python ffmpeg
```

**Windows** — Install Python 3.6+ and add it to your PATH. Install ffmpeg and add it to your PATH ([instructions](http://blog.gregzaal.com/how-to-install-ffmpeg-on-windows/)). Then:
```
py -m pip install subs2cia
```

**Linux (apt-based):**
```
sudo apt install python3 python3-pip ffmpeg
pip3 install subs2cia
```

On WSL, you may need to add `~/.local/bin` to your PATH.

## Condense

```
subs2cia condense -i <input files> [options]
```

### Examples

Condense a video into a dialogue-only audio track and subtitles:
```
subs2cia condense -i "My Video.mkv"
```

Condense with 150ms padding and 1000ms merge threshold, preferring English tracks:
```
subs2cia condense -i video.mkv -p 150 -t 1000 -tl english
```

Use an external subtitle file and output as FLAC, skip subtitle generation:
```
subs2cia condense -i video.mkv "video subtitles.ass" -ae flac --no-gen-subtitle
```

Condense audio with a standalone subtitle file:
```
subs2cia condense -i audio.mp3 subtitles.ass
```

Batch process a directory, ignoring OP/ED, preferring Japanese:
```
subs2cia condense -b -i *.mkv *.srt -I 0m 1m30s -I e2m +1m30s -tl ja -t 1500 -p 100
```

Condense from a JSON transcript (e.g. ElevenLabs Scribe output):
```
subs2cia condense -i audio.mp3 transcript.json -t 1500 -p 200
```

The JSON file is used as the timing source instead of subtitles. Speech segments are determined by gaps between words: wherever the gap exceeds the `-t` threshold, a new segment begins. This works with any language.

### Condense-only options

| Option | Description |
|---|---|
| `-t msecs` | Merge subtitles that start/end within (threshold + 2*padding) ms of each other |
| `-r secs` | Partition input into blocks of this size before condensing |
| `-s secs` | Split condensed output into blocks of this size after condensing |
| `-c <ratio>` | Minimum compression ratio (default 0.2). Rejects subtitle tracks that are too sparse |
| `--no-gen-subtitle` | Don't output a condensed subtitle file |

## SRS Export

```
subs2cia srs -i <input files> [options]
```

### TSV columns

The output TSV file contains one row per subtitle line with the following columns:

| # | Column | Content |
|---|---|---|
| 1 | Subtitle text | The dialogue line |
| 2 | Timestamps | Time range in milliseconds: `start-end` |
| 3 | Audio | `[sound:media_start-end.mp3]` |
| 4 | Screenshot | `<img src='media_start-end.jpg'>` |
| 5 | Video clip | `[sound:media_start-end.mp4]` (requires `--export-video`) |
| 6 | Sources | Comma-separated list of input files |
| 7 | Context | Surrounding subtitle lines separated by `\|` for LLM-assisted study |

### Examples

Basic export from a video file:
```
subs2cia srs -i video.mkv
```

Batch export with normalized audio, saving to a dedicated directory:
```
subs2cia srs -b -i *.mkv *.ja.srt -d srs_export -p 100 -N
```

Export directly to Anki's media folder:
```
subs2cia srs -i video.mkv --media-dir ~/Library/Application\ Support/Anki2/User\ 1/collection.media -d srs_export
```

Export with video clips and a header row:
```
subs2cia srs -i video.mkv --export-video --export-header-row -d srs_export
```

Generate cards from a JSON transcript (Japanese only):
```
subs2cia srs -i audio.mp3 transcript.json -o my_deck
```

When a JSON transcript is used with `srs`, sentences are segmented using MeCab bunsetsu analysis rather than simple timing. This produces one card per sentence, splitting on sentence-ending punctuation (。！？), speaker changes, and long pauses. Commas also trigger splits for longer clauses. This requires the `fugashi` package (see [Optional dependencies](#optional-dependencies)).

### SRS-only options

| Option | Description |
|---|---|
| `-N` | Normalize audio volume across clips |
| `--media-dir <path>` | Save media files to this directory (e.g. Anki's `collection.media`) |
| `--no-export-screenshot` | Skip screenshot export |
| `--no-export-audio` | Skip audio clip export |
| `--export-video` | Export video clips (column 5) |
| `--export-header-row` | Add a header row to the TSV (note: Anki will import it as a card) |

### Anki import instructions

1. In Anki, click **File > Import...**
2. Select the `.tsv` file
3. In the Import dialog:
   - Choose your note type and deck
   - Ensure fields are separated by **Tab**
   - Check **Allow HTML in fields**
   - Map the 7 columns to your note type's fields
   - Click **Import**
4. If audio/screenshots are missing, move the media files into your Anki `collection.media` folder manually, or use `--media-dir` to export directly there.

### Context column and LLMs

The context column (column 7) contains the surrounding subtitle lines (up to 15 lines before and after), separated by pipe characters (`|`). This is useful for providing context to LLMs when generating vocabulary definitions, example sentences, or translations for your flashcards.

## Shared options reference

These options are available for both `condense` and `srs` subcommands.

### Input / Output

| Option | Description |
|---|---|
| `-i <files>` | Input files (video, audio, subtitle, JSON transcript) or a directory |
| `-o <name>` | Output file name (without extension). Ignored in batch mode |
| `-d <path>` | Output directory (default: same as input) |
| `-b` | Batch mode — groups files by name, one output per group |
| `-u` | Dry run — analyze inputs without generating output |
| `-ae <ext>` | Audio extension (default: `mp3`) |
| `-ac <codec>` | Audio codec (default: auto from extension) |
| `-q <kbps>` | Audio bitrate in kbps (default: 320) |

### Stream selection

| Option | Description |
|---|---|
| `-tl <code>` | Prefer streams in this language. Accepts ISO 639-3 codes (`jpn`, `eng`) and BCP 47 locale tags (`zh-TW`, `pt-BR`) |
| `-si <index>` | Force a specific subtitle stream index |
| `-ai <index>` | Force a specific audio stream index |
| `-ls` | List all streams and chapters, then exit |
| `-ma` | Interactive stream picker (overrides `-tl`, `-si`, `-ai`) |

### Audio

| Option | Description |
|---|---|
| `-M` | Mix to mono |
| `-m` | Generate condensed video (CPU intensive) |

### Subtitle filtering

| Option | Description |
|---|---|
| `-ni` | Disable built-in non-dialogue filtering heuristics |
| `-R <regex>` | Ignore subtitle lines matching this regex (overrides built-in filter) |

### Padding and timing

| Option | Description |
|---|---|
| `-p msecs` | Pad each subtitle with this many ms of audio before and after |
| `-I <start> <end>` | Ignore subtitles in this time range (e.g. `-I 0m 1m30s`). Repeatable |
| `-Ic <chapter>` | Ignore subtitles in this chapter title |

### Miscellaneous

| Option | Description |
|---|---|
| `-Q` | Quiet mode — warnings and errors only |
| `-vv` | Debug output |
| `--preset <n>` | Use a built-in preset |
| `-lp` | List available presets |
| `-a` | Print absolute paths |
| `--overwrite-on-demux` | Overwrite existing files when demuxing |
| `--keep-temporaries` | Keep demuxed temporary files |
| `--no-overwrite-on-generation` | Don't overwrite existing generated files |

## subzipper

Rename subtitle files to match video files for Plex-style naming.

```
subzipper -s <subtitle files> -r <reference files> [-l <lang>]
```

### Options

| Option | Description |
|---|---|
| `-s <files>` | Subtitle files to rename |
| `-r <files>` | Reference (video) files to match against |
| `-l <code>` | Language code to append as suffix (e.g. `ja`) |
| `-ns` | Don't sort files alphabetically before matching |
| `-d` | Dry run — print mappings without renaming |
| `-v` | Verbose output |

### Examples

Rename subtitles to match video files with a Japanese language suffix:
```
subzipper -s "episode01.ass" "episode02.ass" -r "MyShow_S01E01.mkv" "MyShow_S01E02.mkv" -l ja
```

Match all subtitle files to all video files in a directory:
```
subzipper -s *.ass -r *.mkv -l ja
```

## JSON transcript input

Instead of subtitle files, you can use transcribed JSON files from speech-to-text services like [ElevenLabs Scribe](https://elevenlabs.io/). The JSON must have this structure:

```json
{
  "language_code": "jpn",
  "words": [
    {"text": "こ", "start": 5.1, "end": 5.16, "type": "word", "speaker_id": "speaker_0", "logprob": -0.001},
    {"text": " ", "start": 5.16, "end": 5.16, "type": "spacing", "speaker_id": "speaker_0", "logprob": 0.0},
    {"text": "[笑い]", "start": 23.0, "end": 23.0, "type": "audio_event", "speaker_id": "speaker_0", "logprob": -0.07}
  ]
}
```

Required fields: `words` array with `text`, `start`, `end`, and `type` for each token. Times are in seconds. Token types: `word` (speech), `spacing` (whitespace, ignored), `audio_event` (non-speech sounds, ignored).

**Condense mode**: Works with any language. Segments speech by timing gaps — wherever the silence between words exceeds the `-t` threshold, a new segment starts.

**SRS mode**: Japanese only (`language_code` must be `jpn` or `ja`). Uses MeCab morphological analysis to split into natural sentences at punctuation, speaker changes, clause boundaries, and long pauses. Requires `fugashi[unidic-lite]`.

## Limitations

- **Bitmap subtitles** (e.g. PGS) are not supported — only text-based subtitle formats supported by ffmpeg and pysubs2
- Subtitle files must be encoded in **UTF-8**
- Subtitles must be **properly aligned** to audio. subs2cia does not perform alignment
- **JSON SRS export** is currently Japanese-only — other languages will be rejected with an error

## About this fork

This is a fork of [dxing97/subs2cia](https://github.com/dxing97/subs2cia) by [@mattvsjapan](https://github.com/mattvsjapan). The original project by Daniel Xing is the foundation for all of this.

### Fork additions

- **JSON transcript input** — use ElevenLabs Scribe JSON files instead of subtitles for both condensed audio and SRS card generation
- **Japanese sentence segmentation** — MeCab-based bunsetsu analysis for natural sentence-level card splitting from JSON transcripts
- **Context column** — 7th TSV column with surrounding subtitle lines for LLM-assisted language learning
- **BCP 47 locale tags** — `-tl zh-TW`, `-tl pt-BR` etc. now work alongside ISO 639-3 codes
- **New SRS options** — `--media-dir`, `--no-export-screenshot`, `--no-export-audio`, `--export-video`, `--export-header-row`
- **Dotted filename fix** — files like `video.v2.mkv` no longer overwrite each other in batch mode
- **Removed pandas dependency** — lighter install, fewer breakage points
