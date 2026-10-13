"""Pobieranie i parsowanie stron tbmp3.pl (zwykły HTML, bez Selenium)."""
import html
import re
import time

import requests

BASE = "https://tbmp3.pl/audycje/"
HEADERS = {"User-Agent": "Mozilla/5.0 (TBMP3 archiwizator)"}

_session = requests.Session()
_session.headers.update(HEADERS)


def pobierz_strone(url, proby=3):
    for proba in range(proby):
        try:
            r = _session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException:
            if proba == proby - 1:
                raise
            time.sleep(2 * (proba + 1))


def tekst(fragment):
    """HTML -> czysty tekst w jednej linii."""
    bez_tagow = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(bez_tagow)).strip()


def _sekcja(strona, naglowek):
    """Zawartość od <h2>naglowek... do następnego <h2> (albo końca main-content)."""
    m = re.search(r"<h2>\s*" + naglowek + r".*?</h2>(.*?)(?=<h2>|end of main-content)", strona, re.S)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- lista audycji

_IKONY = {"fa-mixcloud": "mixcloud", "fa-microphone": "komentarze"}


def lista_audycji(cykl=None, rok=None):
    """Zwraca listę audycji ze strony audycje.php oraz dostępne cykle i lata."""
    params = []
    if rok:
        params.append(f"rok={rok}")
    if cykl:
        params.append(f"cykl={cykl}")
    strona = pobierz_strone(BASE + "audycje.php" + ("?" + "&".join(params) if params else ""))

    cykle = {int(n): tekst(nazwa) for n, nazwa in re.findall(
        r'class="dropdown-item[^"]*" href="audycje\.php\?cykl=(\d+)">(.*?)</a>', strona)}
    aktywny = re.search(r'class="dropdown-item active" href="audycje\.php\?cykl=(\d+)"', strona)
    lata = [int(r) for r in re.findall(r'href="audycje\.php\?rok=(\d{4})&cykl=\d+"', strona)]
    aktywny_rok = re.search(r'top-menu-item active"[^>]*href="audycje\.php\?rok=(\d{4})', strona)

    audycje = []
    for m in re.finditer(
            r'<p><a href="audycja\.php\?audycja=(\d+)">([\d-]+)</a>\s*(<i class="fa ([\w-]+)"></i>)?\s*-\s*(.*?)</p>',
            strona):
        audycje.append({
            "id": int(m.group(1)),
            "data": m.group(2),
            "dostepnosc": _IKONY.get(m.group(4), "brak"),
            "tytul": tekst(m.group(5)),
        })
    return {
        "cykl": int(aktywny.group(1)) if aktywny else cykl,
        "rok": int(aktywny_rok.group(1)) if aktywny_rok else rok,
        "cykle": cykle,
        "lata": lata,
        "audycje": audycje,
    }


# ---------------------------------------------------------------- jedna audycja

def _link(fragment, rodzaj):
    m = re.search(r'href="[^"]*' + rodzaj + r'\.php\?\w+=\d+">(.*?)</a>', fragment, re.S)
    return tekst(m.group(1)) if m else None


def klasyfikuj(tekst_pozycji, mp3):
    t = tekst_pozycji.lower()
    if mp3:
        return "komentarz"  # plik z tbmp3 (czasem z muzyką lub sygnałem w tle)
    if "komentarz" in t:
        return "komentarz"  # komentarz bez pliku na stronie
    if t.startswith("sygnał") or t.startswith("sygnal") or ("sygnał" in t and " - " not in t):
        return "sygnal"
    return "utwor"


def _zapytanie(poz):
    """Zapytanie do wyszukiwarki YouTube na podstawie linków z opisu."""
    if not poz["wykonawca"]:
        return re.sub(r"\s*-\s*muzyka (do|z) filmu.*$", "", poz["tekst"])
    czesci = [poz["wykonawca"]]
    if poz["utwor"]:
        czesci.append(poz["utwor"])
    if poz["film"]:
        film = re.sub(r"\s*\(\d{4}\)\s*$", "", poz["film"])
        czesci.append(f"{film} soundtrack" if poz["utwor"] else film)
    return " - ".join(czesci)


def _pozycje(opis_html):
    """Dzieli sekcję 'Opis' po znacznikach <p (HTML na stronie jest źle zagnieżdżony)."""
    pozycje = []
    for kawalek in re.split(r"(?=<p[\s>])", opis_html):
        dlugi = kawalek.startswith('<p class="long-comment"')
        tresc = tekst(kawalek)
        if dlugi:
            if pozycje and tresc:
                poprz = pozycje[-1]
                poprz["transkrypcja"] = (poprz.get("transkrypcja", "") + "\n" + tresc).strip()
            continue
        m = re.match(r"(\d+)\.\s*(.*)", tresc)
        if not m:
            continue
        mp3 = re.search(r"openAudioPlayer\('([^']+)'\)", kawalek)
        mp3 = mp3.group(1).replace("http://", "https://") if mp3 else None
        opis = m.group(2).strip()
        poz = {
            "nr": int(m.group(1)),
            "tekst": opis,
            "typ": klasyfikuj(opis, mp3),
            "wykonawca": _link(kawalek, "wykonawca"),
            "utwor": _link(kawalek, "utwor"),
            "film": _link(kawalek, "film"),
            "mp3": mp3,
        }
        if poz["typ"] == "utwor":
            poz["zapytanie"] = _zapytanie(poz)
        pozycje.append(poz)
    return pozycje


def audycja(audycja_id):
    url = f"{BASE}audycja.php?audycja={audycja_id}"
    strona = pobierz_strone(url)

    h1 = re.search(r'<div class="col-sm-8 main-content">.*?<h1>(.*?)</h1>', strona, re.S)
    if not h1:
        raise ValueError(f"Nie znaleziono audycji {audycja_id} ({url})")
    czesci = h1.group(1).split("<br/>")
    tytul = tekst(czesci[0])
    data = re.search(r"\d{4}-\d{2}-\d{2}", czesci[1]).group(0) if len(czesci) > 1 else None
    cykl_m = re.search(r'cykl=(\d+)">(.*?)</a>', czesci[2]) if len(czesci) > 2 else None

    mixcloud = re.search(r"feed=(https://www\.mixcloud\.com/[^&'\"]+)", strona)
    okladka = re.search(rf'<img[^>]+src="(imga/{audycja_id}\.\w+)"', strona)
    plyty = [tekst(p) for p in re.findall(r"<p>(.*?)</p>", _sekcja(strona, "Płyty"))]

    return {
        "id": int(audycja_id),
        "url": url,
        "tytul": tytul,
        "data": data,
        "cykl": tekst(cykl_m.group(2)) if cykl_m else None,
        "cykl_id": int(cykl_m.group(1)) if cykl_m else None,
        "mixcloud": mixcloud.group(1) if mixcloud else None,
        "okladka": BASE + okladka.group(1) if okladka else None,
        "komentarz": tekst(_sekcja(strona, "Komentarz")),
        "plyty": [p for p in plyty if p],
        "pozycje": _pozycje(_sekcja(strona, "Opis")),
    }
