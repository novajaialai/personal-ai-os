#!/usr/bin/env bash
# Push-to-talk hotkey for the AIOS voice endpoint (Phase 5, runbook-phase5.md §5.3).
# Bind this to a key: hold to record, release (or Ctrl-C the recorder) to send.
#
# Usage: ./voice-hotkey.sh [session_id]
#
# Requires: sox (arecord alternative that works on both Linux and macOS),
# curl, and a player (ffplay preferred, afplay on macOS as fallback).
set -euo pipefail

AIOS_URL="${AIOS_URL:-https://aios-jake-1.tail828365.ts.net}"
SESSION_ID="${1:-$(cat ~/.aios-voice-session 2>/dev/null || true)}"
TMP_AUDIO="$(mktemp /tmp/aios-voice-XXXX.wav)"
TMP_REPLY="$(mktemp /tmp/aios-reply-XXXX.mp3)"
trap 'rm -f "$TMP_AUDIO" "$TMP_REPLY"' EXIT

if ! command -v sox >/dev/null; then
  echo "Install sox first: dnf install sox (Fedora) / brew install sox (Mac)" >&2
  exit 1
fi

echo "Recording — press Ctrl-C when done speaking..."
sox -d "$TMP_AUDIO" 2>/dev/null || true   # sox exits nonzero on SIGINT, that's expected

echo "Sending..."
ARGS=(-sf -X POST "$AIOS_URL/voice" -F "audio=@$TMP_AUDIO;filename=audio.wav")
if [[ -n "$SESSION_ID" ]]; then
  ARGS+=(-F "session_id=$SESSION_ID")
fi

RESP_HEADERS="$(mktemp)"
curl "${ARGS[@]}" -D "$RESP_HEADERS" -o "$TMP_REPLY"

NEW_SID=$(grep -i '^x-session-id:' "$RESP_HEADERS" | cut -d' ' -f2 | tr -d '\r')
TRANSCRIPT=$(grep -i '^x-transcript:' "$RESP_HEADERS" | cut -d' ' -f2- | tr -d '\r')
REPLY=$(grep -i '^x-reply-text:' "$RESP_HEADERS" | cut -d' ' -f2- | tr -d '\r')
rm -f "$RESP_HEADERS"

[[ -n "$NEW_SID" ]] && echo "$NEW_SID" > ~/.aios-voice-session

echo "You: $(python3 -c "import urllib.parse,sys; print(urllib.parse.unquote(sys.argv[1]))" "$TRANSCRIPT" 2>/dev/null || echo "$TRANSCRIPT")"
echo "AIOS: $(python3 -c "import urllib.parse,sys; print(urllib.parse.unquote(sys.argv[1]))" "$REPLY" 2>/dev/null || echo "$REPLY")"

if command -v ffplay >/dev/null; then
  ffplay -nodisp -autoexit -loglevel quiet "$TMP_REPLY"
elif command -v afplay >/dev/null; then
  afplay "$TMP_REPLY"
else
  echo "No player found (install ffmpeg or use macOS afplay) — reply audio at $TMP_REPLY" >&2
fi
