---
name: audycja
description: Agent odtwarzający audycje Tomasza Beksińskiego z tbmp3.pl — pyta o audycję i preferencje, planuje pracę, pobiera komentarze, utwory, sygnały i składa jeden opisany plik. Użyj, gdy użytkownik chce pobrać/odtworzyć/złożyć audycję, dodać sygnały albo poprawić gotową audycję.
argument-hint: "[id audycji | data | tytuł]"
---

# Agent audycji TB

Pracujesz jako agent, który odtwarza audycję radiową Tomasza Beksińskiego. Rozmawiasz po polsku.
Wszystkie operacje robisz narzędziem `./tb` (uruchamiane z katalogu projektu; `./tb <komenda> -h` = pomoc).
Stan audycji jest w `audycje/<folder>/manifest.json` — nie edytuj go ręcznie, używaj `./tb ustaw/dodaj/plik`.

Zasady:
- **Pytaj przez AskUserQuestion**, gdy decyzja należy do użytkownika. Grupuj pytania (do 4 naraz), dawaj rekomendację jako pierwszą opcję. Nie pytaj o rzeczy, które sam ustalisz z danych.
- **Najpierw plan, potem praca.** Zanim cokolwiek pobierzesz, pokaż plan i poczekaj na akceptację.
- **Oryginały są nietykalne.** `oryginaly/` to źródła; obróbka zawsze idzie na kopiach w `przetworzone/`.
- Na koniec każdego etapu krótko raportuj: co zrobione, co brakuje, co dalej.

## Etap 1 — wybór audycji

Argument skilla: `$ARGUMENTS`.
- Liczba → to ID audycji.
- Data/tytuł/cykl/rok → znajdź przez `./tb lista --cykl N --rok R [--szukaj TEKST] [--dostepne]`
  (bez `--cykl` pokazuje listę cykli; M = cała na Mixcloud, K = komentarze mp3, - = tylko opis).
- Pusto → zapytaj, czego szuka (cykl, rok, temat), zaproponuj kilka audycji z oznaczeniem dostępności.

## Etap 2 — rozpoznanie

`./tb info ID` → tworzy manifest i pokazuje wszystkie pozycje. Przeanalizuj:
- ile komentarzy z mp3, ile komentarzy BEZ pliku, ile utworów, ile sygnałów,
- czy jest Mixcloud,
- **przeczytaj transkrypcje komentarzy** w `manifest.json` (pole `transkrypcja`) i opis audycji —
  Tomasz często mówi, z jakiej płyty/wersji jest utwór (koncert, remix, singiel, rok). To decyduje o wyborze wersji.
- pozycje mieszane, np. „Utwór - Komentarz Tomasza” (komentarz na tle muzyki — ma własny mp3, NIE szukaj osobno utworu),
  „Komentarz Tomasza i sygnał serwisu Trójki” (sygnał już jest w nagraniu komentarza).
- Jeśli folder audycji już istnieje — `./tb status ID` i kontynuuj od miejsca, gdzie skończono.

## Etap 3 — pytania i plan

Zapytaj (AskUserQuestion) tylko o to, co dotyczy tej audycji:
1. **Mixcloud** (jeśli jest): pobrać całą audycję z Mixcloud zamiast/obok składania? (komentarze bez pliku istnieją wtedy tylko w nagraniu z Mixcloud)
2. **Komentarze bez pliku**: pominąć czy zostawić slot na później?
3. **Wybór wersji utworów**: agent dobiera sam i pokazuje listę do akceptacji (rekomendowane) / pytać przy każdym wątpliwym / pełny automat (`./tb utwory`).
4. **Obróbka**: wyrównanie głośności + przycinanie ciszy (domyślnie tak), crossfade (ile s), odszumianie komentarzy, format m4b (rozdziały) czy mp3.
5. **Sygnały**: pokaż `./tb sygnaly`. Sygnały z listy na stronie mają swoje pozycje; zapytaj, czy dodać dodatkowe (np. sygnał audycji na początku i końcu) i z których plików. Jeśli biblioteka pusta — slot zostaje na później.

Zapisz preferencje obróbki: `./tb opcje ID [--crossfade 1.5] [--odszumiaj] [--format mp3] ...`.
Pokaż plan w punktach (co pobierasz, skąd, ile pozycji, co zostaje na później) i poproś o akceptację.

## Etap 4 — pobieranie

1. `./tb komentarze ID` — komentarze z tbmp3.pl.
2. Utwory — dla każdej pozycji typu ♪:
   - `./tb szukaj ID NR [--zapytanie "..."]` → wybierz kandydata. Kryteria: zgodny wykonawca i tytuł, wersja zgodna z kontekstem
     (live tylko gdy audycja/transkrypcja mówi o koncercie; muzyka filmowa — oryginalna ścieżka dźwiękowa), kanał „- Topic”/oficjalny preferowany,
     rozsądna długość (nie „full album”, nie 1-godzinne mixy), bez coverów/karaoke/reaction.
   - Gdy nic nie pasuje — spróbuj innego zapytania (`--zapytanie`), a jak dalej nic: zapisz `./tb ustaw ID NR --uwagi "..."` i zapytaj użytkownika (może mieć plik: `./tb plik ID NR ścieżka`).
   - `./tb utwor ID NR URL`.
   - Przy wielu utworach pokazuj wybory partiami (tabela: nr, utwór, wybrany tytuł YT, czas), żeby użytkownik mógł zakwestionować.
3. Sygnały: `./tb plik ID NR nazwa_z_biblioteki` albo `./tb dodaj ID --po N --tekst "Sygnał audycji" [--plik ...]`.
4. Mixcloud (jeśli wybrano): `./tb mixcloud ID` (długo — uruchom w tle).

Pobieranie wielu utworów może trwać — przy dłuższych seriach uruchamiaj w tle i raportuj postęp.

## Etap 5 — obróbka i złożenie

1. `./tb status ID` — sprawdź braki.
2. Braki → zapytaj: uzupełnić teraz / złożyć bez nich (`--pomin-brakujace`; slot zostaje w manifeście i można złożyć ponownie później).
3. `./tb zloz ID` (wymaga ffmpeg; jeśli go brak — powiedz, żeby użytkownik wpisał `! sudo apt install ffmpeg`).
   Obróbka jest cache'owana, więc ponowne złożenie po dodaniu sygnału jest szybkie.
   Po udanym złożeniu `zloz` sam kopiuje plik `.m4b` na pulpit Windows (`TBMP3_EKSPORT`, domyślnie wykryty pulpit);
   `--bez-eksportu` wyłącza, `./tb eksport ID` kopiuje ponownie.
4. Raport końcowy: ścieżka pliku (lokalna i na pulpicie), czas trwania, liczba rozdziałów, czego brakuje, co można jeszcze poprawić.

## Poprawki później

- Zła wersja utworu: `./tb szukaj` + `./tb utwor ID NR NOWY_URL` (stary plik zostaje zastąpiony), potem `./tb zloz ID`.
- Dodanie sygnałów do gotowej audycji: `./tb plik`/`./tb dodaj`, potem `./tb zloz ID`.
- Zmiana obróbki: `./tb opcje ID ...`, potem `./tb zloz ID`.
