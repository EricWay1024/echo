# écho

**Learn a language by shadowing real YouTube audio — with a transcript you can actually trust.**

écho is a small app you run on your own computer. Paste a YouTube link and it gives
you the audio plus a clean, perfectly-timed transcript to shadow, look things up in,
and turn into flashcards you'll actually remember. It's built for **French (B2+)**
and brings its own AI smarts through your own Anthropic API key.

> **Heads-up:** this is a personal, local-first tool — you run it on your machine,
> there's no website to sign up for, and the AI features use your own API key (a few
> cents per video). It's currently tuned for French.

## Why écho?

If you've tried shadowing from YouTube, you know the problem: auto-captions are
timed to the audio but full of mistakes and chopped into awkward chunks. Clean them
up and you usually *lose the timing* — so karaoke highlighting and sentence looping
stop working.

écho cleans up the captions with AI **without ever losing the timing.** Every word —
even the corrected ones — stays locked to the exact moment it's spoken. So you get a
trustworthy transcript *and* word-perfect playback: tap any word to jump there, loop
a sentence until it's yours, and watch the highlight track right along.

## What you can do

**🗣️ Shadow.** Play with a word-by-word karaoke highlight. Click any word to jump to
it. Loop a clause A–B until you nail it, or use **step mode** to pause after each
sentence and repeat it back. Slow things down (pitch preserved), or hide the text
and train your ears first.

**🔤 Hear how it's said.** Click a word for its IPA pronunciation — with French
liaison shown at the clause level. No more guessing how a conjugated form sounds.

**🖍️ Mark as you go.** Select anything you're unsure of and flag it — 🔊 for
pronunciation, ❓ for meaning — with an optional note. It's instant and never breaks
your flow.

**🌐 Understand on demand.** Stuck on a sentence? Reveal its translation (中文 or
English) with one click. It's hidden by default, so you attempt it yourself first.

**💡 Get explanations.** Everything you mark ❓ gets a focused, B2-level explanation
(the dictionary form, how it's used here, collocations, false friends) — generated
in the background while you shadow, so it's ready when you finish.

**🃏 Build flashcards.** écho drafts Anki cards from your marks — cloze cards with a
hint, plus vocab/grammar cards and **audio cards clipped from the real sentence**.
Keep the ones you like and export to Anki (`.apkg` with audio, or `.tsv`).

**🔁 …or review right here.** Skip the export and study in-app: a built-in
spaced-repetition system plays the **original clause as the prompt** and lets you
jump straight back to where the word appeared in the video — because a word is
easiest to remember where you met it.

**⏯️ Pick up where you left off.** écho remembers your place in every video.

## Get started

You'll need **Python 3.12** + [uv](https://docs.astral.sh/uv/), **Node 20+**,
**ffmpeg**, and an **Anthropic API key**. (To import from YouTube you'll also want
**yt-dlp** + **Deno**; for clause-level IPA, optionally **espeak-ng**.)

```bash
# 1. install
uv sync
npm install --prefix web && npm run build --prefix web

# 2. configure (both files stay out of git)
cp config.toml.example config.toml
printf 'ANTHROPIC_API_KEY=sk-ant-...\n' > .env

# 3. run
uv run python -m echo        # then open http://localhost:7777
```

System tools (Debian/Ubuntu):

```bash
sudo apt-get install -y ffmpeg espeak-ng        # ffmpeg required, espeak optional
uv tool install yt-dlp                          # ┐ to import
curl -fsSL https://deno.land/install.sh | sh    # ┘ from YouTube
```

Tip: `chrome --app=http://localhost:7777` opens it in a clean, browser-chrome-free
window.

## A typical session

1. **Add a video** — paste a YouTube URL in the library.
2. **Rectify & segment** — one click runs the AI cleanup; now you have clean, timed clauses.
3. **Shadow** — loop, step, slow down, and mark the tricky bits.
4. **Review** — read the translations, skim the explanations, keep the flashcards worth keeping.
5. **Revise** — drill your due cards with spaced repetition, in context, any day.

## Configuration

`config.toml` holds your learner profile (the languages you know and your target),
which AI model to use, your preferred explanation language (`explain_lang`, default
中文), and where to store data. Your API key lives in `.env`, never in the config.

## Under the hood (for the curious)

A Python + FastAPI backend, a React single-page app it serves itself, and SQLite
plus a local audio cache. The key trick: the AI returns *edits over word indices and
clause boundaries* — never rewritten prose — so the original timing is never lost,
and every AI result is cached so you only ever pay once. Want to hack on it? See
[CLAUDE.md](CLAUDE.md) for the engineering guide and [`plan/`](plan/) for the design.

## Status & scope

A personal, single-user tool, currently focused on **French**. The pipeline is
mostly language-agnostic, but the prompts and pronunciation data assume French.
Costs: roughly a few cents per video to rectify and per explanation; translations
are fractions of a cent — and it's all cached, so you never pay twice.

## Acknowledgements

- [Lexique 3.83](http://www.lexique.org) — French pronunciation + frequency data
  (see `echo/data/LEXIQUE_NOTICE.md`)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) ·
  [espeak-ng](https://github.com/espeak-ng/espeak-ng) ·
  [phonemizer](https://github.com/bootphon/phonemizer) ·
  [genanki](https://github.com/kerrickstaley/genanki) ·
  [Anthropic](https://www.anthropic.com)

## License

[MIT](LICENSE) © 2026 Yuhang Wei.
