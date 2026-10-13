# TBMP3 — audycje Tomasza Beksińskiego

Odtwarzanie audycji z https://tbmp3.pl: komentarze Tomasza (mp3 z tbmp3.pl) + utwory (YouTube przez yt-dlp)
+ sygnały (lokalna biblioteka) → jeden opisany plik (m4b/mp3 z rozdziałami, tagami, okładką).

- Agent: skill `/audycja` (`.claude/skills/audycja/SKILL.md`) — prowadzi użytkownika krok po kroku.
- Narzędzie: `./tb <komenda>` (pakiet `tbmp3/`, venv w `venv/`). Pomoc: `./tb -h`.
  - `scraper.py` — parsowanie tbmp3.pl (zwykły HTML; strona ma źle zagnieżdżone `<p>`, dlatego dzielimy po znacznikach, nie DOM).
  - `manifest.py` — `audycje/<data skrót - tytuł>/manifest.json`: pozycje ze strony + `dodatkowe` (wstawione sygnały, nr np. `0a`).
  - `pobieranie.py` — komentarze, YouTube, Mixcloud, sygnały.
  - `audio.py` — ffmpeg: przycinanie ciszy, odszumianie, loudnorm 2-przebiegowo, scalanie (concat / acrossfade), rozdziały.
- Dane: `audycje/` (wyniki), `sygnaly/` (biblioteka sygnałów) — poza gitem.
- Gotowy plik `.m4b` jest po `./tb zloz` kopiowany na pulpit Windows (WSL; `TBMP3_EKSPORT` nadpisuje cel).
- Wymagania systemowe: ffmpeg (`sudo apt install ffmpeg`).
- Oryginały (`oryginaly/`) nigdy nie są modyfikowane; obróbka tylko na kopiach w `przetworzone/`.
