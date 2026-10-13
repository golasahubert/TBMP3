"""Obróbka dźwięku przez ffmpeg: przycinanie ciszy, odszumianie, normalizacja, scalanie z rozdziałami."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import mutagen

from .manifest import etykieta

ROZSZERZENIA = {".mp3", ".m4a", ".webm", ".opus", ".ogg", ".wav", ".flac", ".aac", ".wma"}

DOMYSLNE = {
    "normalizuj": True,     # EBU R128, dwuprzebiegowo
    "glosnosc": -16.0,      # LUFS docelowo
    "przytnij": True,       # cisza na początku i końcu
    "prog_ciszy": -50,      # dB
    "odszumiaj": False,     # tylko komentarze i sygnały (stare taśmy)
    "crossfade": 0.0,       # sekundy, 0 = twarde cięcia
    "format": "m4b",        # m4b (rozdziały w każdym odtwarzaczu audiobooków) albo mp3
    "bitrate": "160k",
}

TYPY_Z_TASMY = {"komentarz", "sygnal"}


def ffmpeg():
    sciezka = shutil.which("ffmpeg")
    if not sciezka:
        raise SystemExit("Brak ffmpeg. Zainstaluj: sudo apt install ffmpeg")
    return sciezka


def _uruchom(argumenty, zwroc_stderr=False):
    wynik = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", *argumenty],
                           capture_output=True, text=True)
    if wynik.returncode != 0:
        raise RuntimeError("ffmpeg: " + wynik.stderr.strip().splitlines()[-1] if wynik.stderr else "błąd")
    return wynik.stderr if zwroc_stderr else None


def czas_trwania(plik):
    info = mutagen.File(plik)
    if info is not None and getattr(info, "info", None) and info.info.length:
        return float(info.info.length)
    # awaryjnie: ffmpeg zdekoduje całość i poda czas
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(plik), "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    czasy = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)
    h, m, s = czasy[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def _filtry(poz, opcje):
    f = []
    if opcje["odszumiaj"] and poz["typ"] in TYPY_Z_TASMY:
        f += ["highpass=f=60", "afftdn=nf=-25"]
    if opcje["przytnij"]:
        cisza = (f"silenceremove=start_periods=1:start_duration=0.1:"
                 f"start_threshold={opcje['prog_ciszy']}dB")
        f += [cisza, "areverse", cisza, "areverse"]
    return f


def _zmierz_glosnosc(plik, filtry, opcje):
    lf = f"loudnorm=I={opcje['glosnosc']}:TP=-1.5:LRA=11:print_format=json"
    err = _uruchom(["-i", str(plik), "-af", ",".join(filtry + [lf]), "-f", "null", "-"], True)
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def przetworz(poz, wejscie: Path, katalog: Path, opcje, szer):
    """Tworzy przetworzoną kopię WAV (oryginał nietknięty). Wynik jest cache'owany."""
    katalog.mkdir(parents=True, exist_ok=True)
    wyjscie = katalog / f"{etykieta(poz, szer)}.wav"
    klucz = {"zrodlo": str(wejscie), "rozmiar": wejscie.stat().st_size,
             "mtime": wejscie.stat().st_mtime, "filtry": _filtry(poz, opcje),
             "normalizuj": opcje["normalizuj"], "glosnosc": opcje["glosnosc"]}
    meta = wyjscie.with_suffix(".json")
    if wyjscie.exists() and meta.exists() and json.loads(meta.read_text()) == klucz:
        return wyjscie

    filtry = _filtry(poz, opcje)
    if opcje["normalizuj"]:
        m = _zmierz_glosnosc(wejscie, filtry, opcje)
        filtry.append(
            f"loudnorm=I={opcje['glosnosc']}:TP=-1.5:LRA=11:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    argumenty = ["-y", "-i", str(wejscie), "-vn"]
    if filtry:
        argumenty += ["-af", ",".join(filtry)]
    _uruchom(argumenty + ["-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(wyjscie)])
    meta.write_text(json.dumps(klucz))
    return wyjscie


# ------------------------------------------------------------------ scalanie

def _esc(tekst):
    return re.sub(r"([=;#\\\n])", r"\\\1", str(tekst))


def tytul_rozdzialu(poz):
    if poz["typ"] == "utwor" and poz.get("wykonawca") and poz.get("utwor"):
        return f'{poz["wykonawca"]} - {poz["utwor"]}'
    return poz["tekst"]


def _hms(s):
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def opis_tekstowy(a, rozdzialy):
    d = a.dane
    linie = [f'{d["tytul"]}', f'{d["cykl"] or ""} — {d["data"]}', "Tomasz Beksiński", d["url"], ""]
    if d.get("komentarz"):
        linie += [d["komentarz"], ""]
    linie.append("Lista:")
    for start, poz in rozdzialy:
        linie.append(f"  {_hms(start)}  {etykieta(poz, a.szerokosc_nr)}. {tytul_rozdzialu(poz)}")
    pominiete = [p for p in a.kolejnosc() if p.get("pomin")]
    if pominiete:
        linie += ["", "Pominięte: " + ", ".join(f'{etykieta(p)}. {tytul_rozdzialu(p)}' for p in pominiete)]
    transkrypcje = [p for p in a.kolejnosc() if p.get("transkrypcja")]
    if transkrypcje:
        linie += ["", "Komentarze Tomasza:"]
        for p in transkrypcje:
            linie += ["", f"[{etykieta(p, a.szerokosc_nr)}] {p['transkrypcja']}"]
    return "\n".join(linie) + "\n"


def zloz(a, opcje, okladka=None, postep=print):
    """Scala przetworzone pozycje w jeden opisany plik. Zwraca (ścieżka, czas, rozdziały)."""
    szer = a.szerokosc_nr
    pozycje = [p for p in a.kolejnosc() if not p.get("pomin") and a.sciezka(p)]
    if not pozycje:
        raise SystemExit("Nie ma żadnych plików do złożenia.")

    pliki = []
    for i, p in enumerate(pozycje, 1):
        postep(f"  [{i}/{len(pozycje)}] obróbka {etykieta(p, szer)} {tytul_rozdzialu(p)[:60]}")
        pliki.append(przetworz(p, a.sciezka(p), a.przetworzone, opcje, szer))
    czasy = [czas_trwania(f) for f in pliki]

    cf = float(opcje["crossfade"] or 0)
    rozdzialy, t = [], 0.0
    for i, (p, c) in enumerate(zip(pozycje, czasy)):
        rozdzialy.append((t, p))
        t += c - (cf if i < len(pozycje) - 1 else 0)
    calosc = t

    # metadane ffmpeg (tagi globalne + rozdziały)
    d = a.dane
    meta = [";FFMETADATA1",
            f"title={_esc(d['tytul'] + ' (' + d['data'] + ')')}",
            "artist=Tomasz Beksiński", "album_artist=Tomasz Beksiński",
            f"album={_esc(d['cykl'] or 'Audycje Tomasza Beksińskiego')}",
            f"date={d['data']}", "genre=Audycja radiowa",
            f"comment={_esc((d.get('komentarz') or '') + ' ' + d['url'])}",
            f"description={_esc(opis_tekstowy(a, rozdzialy)[:4000])}"]
    for i, (start, p) in enumerate(rozdzialy):
        koniec = rozdzialy[i + 1][0] if i + 1 < len(rozdzialy) else calosc
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start * 1000)}",
                 f"END={int(koniec * 1000)}", f"title={_esc(tytul_rozdzialu(p))}"]
    plik_meta = a.przetworzone / "metadane.txt"
    plik_meta.write_text("\n".join(meta) + "\n", encoding="utf-8")

    fmt = opcje["format"]
    wyjscie = a.folder / f"{a.folder.name}.{fmt}"
    tmp = wyjscie.with_name(wyjscie.stem + ".tmp." + fmt)

    wyjsciowe = []
    if cf > 0 and len(pliki) > 1:
        wejscia = sum((["-i", str(f)] for f in pliki), [])
        lancuch, poprz = [], "[0:a]"
        for i in range(1, len(pliki)):
            d_cf = min(cf, czasy[i - 1] / 2, czasy[i] / 2)
            wyj = f"[x{i}]"
            lancuch.append(f"{poprz}[{i}:a]acrossfade=d={d_cf:.3f}:c1=tri:c2=tri{wyj}")
            poprz = wyj
        wyjsciowe += ["-filter_complex", ";".join(lancuch), "-map", poprz]
        n_meta = len(pliki)
    else:
        lista = a.przetworzone / "lista.txt"
        lista.write_text("".join(f"file '{f.name}'\n" for f in pliki), encoding="utf-8")
        wejscia = ["-f", "concat", "-safe", "0", "-i", str(lista)]
        wyjsciowe += ["-map", "0:a"]
        n_meta = 1

    wejscia += ["-i", str(plik_meta)]
    if okladka:
        wejscia += ["-i", str(okladka)]
        wyjsciowe += ["-map", f"{n_meta + 1}:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
    wyjsciowe += ["-map_metadata", str(n_meta), "-map_chapters", str(n_meta)]
    if fmt == "mp3":
        wyjsciowe += ["-c:a", "libmp3lame", "-b:a", opcje["bitrate"], "-id3v2_version", "3"]
    else:
        wyjsciowe += ["-c:a", "aac", "-b:a", opcje["bitrate"], "-movflags", "+faststart", "-f", "mp4"]
    argumenty = wejscia + wyjsciowe

    postep(f"  scalanie {len(pliki)} plików → {wyjscie.name}")
    _uruchom(["-y", *argumenty, str(tmp)])
    tmp.replace(wyjscie)
    (a.folder / "opis.txt").write_text(opis_tekstowy(a, rozdzialy), encoding="utf-8")
    return wyjscie, calosc, rozdzialy
