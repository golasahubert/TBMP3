"""Pobieranie: komentarze z tbmp3.pl, utwory z YouTube, całe audycje z Mixcloud, sygnały z biblioteki."""
import shutil
from pathlib import Path

import yt_dlp

from . import audio
from .manifest import SYGNALY, nazwa_pozycji
from .scraper import _session

# Bez ffmpeg bierzemy gotowy strumień (m4a/webm) — oryginał bez ponownej kompresji.
FORMAT_AUDIO = "bestaudio[ext=m4a]/bestaudio/best"


def _pobierz_plik(url, cel: Path):
    tmp = cel.with_suffix(cel.suffix + ".part")
    with _session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for blok in r.iter_content(1 << 16):
                f.write(blok)
    tmp.rename(cel)


def komentarze(a, tylko=None):
    """Pobiera komentarze, które mają plik mp3 na tbmp3.pl. Zwraca (pobrane, pominięte, błędy)."""
    a.oryginaly.mkdir(parents=True, exist_ok=True)
    pobrane, bylo, bledy = [], [], []
    for p in a.dane["pozycje"]:
        if not p.get("mp3") or (tylko and p["nr"] not in tylko):
            continue
        if a.sciezka(p):
            bylo.append(p["nr"])
            continue
        cel = a.oryginaly / (nazwa_pozycji(p, a.szerokosc_nr) + ".mp3")
        try:
            _pobierz_plik(p["mp3"], cel)
        except Exception as e:  # noqa: BLE001 — raportujemy i jedziemy dalej
            bledy.append((p["nr"], str(e)))
            continue
        p["plik"] = str(cel.relative_to(a.folder))
        p["zrodlo"] = p["mp3"]
        a.zapisz()
        pobrane.append(p["nr"])
        print(f"  ✓ {p['nr']:>3} {cel.name}")
    return pobrane, bylo, bledy


def szukaj(zapytanie, ile=5):
    """Kandydaci z YouTube (bez pobierania): tytuł, kanał, czas, URL."""
    opcje = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opcje) as ydl:
        wynik = ydl.extract_info(f"ytsearch{ile}:{zapytanie}", download=False)
    return [{
        "tytul": w.get("title"),
        "kanal": w.get("channel") or w.get("uploader"),
        "czas": int(w["duration"]) if w.get("duration") else None,
        "url": w.get("url") or f"https://www.youtube.com/watch?v={w['id']}",
    } for w in wynik.get("entries", [])]


def _yt_pobierz(url, szablon: Path):
    opcje = {
        "format": FORMAT_AUDIO,
        "outtmpl": str(szablon) + ".%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opcje) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info)), info


def utwor(a, p, url):
    """Pobiera utwór dla pozycji p z podanego URL (YouTube lub cokolwiek, co obsługuje yt-dlp)."""
    a.oryginaly.mkdir(parents=True, exist_ok=True)
    stary = a.sciezka(p)
    sciezka, info = _yt_pobierz(url, a.oryginaly / nazwa_pozycji(p, a.szerokosc_nr))
    if stary and stary != sciezka:
        stary.unlink()  # zamiana na inną wersję
    p["plik"] = str(sciezka.relative_to(a.folder))
    p["zrodlo"] = {"url": info.get("webpage_url", url), "tytul": info.get("title"),
                   "kanal": info.get("channel") or info.get("uploader"), "czas": info.get("duration")}
    a.zapisz()
    return sciezka


def mixcloud(a):
    """Pobiera pełną audycję z Mixcloud do folderu audycji (obok składanki)."""
    if not a.dane.get("mixcloud"):
        raise SystemExit("Ta audycja nie ma nagrania na Mixcloud.")
    sciezka, info = _yt_pobierz(a.dane["mixcloud"], a.folder / f"{a.folder.name} (Mixcloud)")
    a.dane["mixcloud_plik"] = sciezka.name
    a.zapisz()
    return sciezka, info.get("duration")


def okladka(a):
    if not a.dane.get("okladka"):
        return None
    cel = a.folder / ("okladka" + Path(a.dane["okladka"]).suffix)
    if not cel.exists():
        try:
            _pobierz_plik(a.dane["okladka"], cel)
        except Exception:  # noqa: BLE001 — okładka jest opcjonalna
            return None
    return cel


def biblioteka_sygnalow():
    if not SYGNALY.exists():
        return []
    return sorted(p for p in SYGNALY.iterdir() if p.suffix.lower() in audio.ROZSZERZENIA)


def przypisz_plik(a, p, plik):
    """Kopiuje wskazany plik (np. sygnał z biblioteki) do oryginałów i przypisuje do pozycji."""
    zrodlo = Path(plik).expanduser()
    if not zrodlo.exists():
        kandydat = SYGNALY / plik
        if not kandydat.exists():
            raise SystemExit(f"Nie ma pliku: {plik}")
        zrodlo = kandydat
    a.oryginaly.mkdir(parents=True, exist_ok=True)
    stary = a.sciezka(p)
    cel = a.oryginaly / (nazwa_pozycji(p, a.szerokosc_nr) + zrodlo.suffix.lower())
    if stary and stary != cel:
        stary.unlink()
    shutil.copy2(zrodlo, cel)
    p["plik"] = str(cel.relative_to(a.folder))
    p["zrodlo"] = str(zrodlo)
    a.zapisz()
    return cel
