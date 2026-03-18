# Bo-Projektstart
(Hack test)
Dieses Repository enthält ein QGIS-Plugin-Grundgerüst für **Bo-Projektstart / Musterprojekt-Erstellung**.

## Überblick

### Kategorien

- **Layer**: Kategorisierte Layerauswahl mit mindestens 2 Ebenen (Kategorie → Gruppe → Layer), inkl. Name, Kurzbeschreibung und Typ
- **Layouts**: Auswahl von Layouts mit Name und Beschreibung. Gewählte `.qpt`-Layouts werden in den QGIS-Layout-Manager importiert
- **Einstellungen**: Plugin-Konfiguration und Benutzer-Stammdaten

### Funktionen

- JSON-basierter Layer-/Layout-Katalog (`default_catalog.json`)
- Katalog-Reader normalisiert und validiert Katalogdaten (inkl. einfacher Rückwärtskompatibilität für ältere JSON-Strukturen)
- Server-Settings in `settings.json` (vom Anwender separat ladbar, z. B. mit verschlüsseltem Inhalt)
- Lokale Benutzer-/Systemdaten in `user_profile.json` (z. B. Cache-Pfad und Stammdaten)
- Lokaler Arbeitskatalog in `local_catalog.json` (wird automatisch erzeugt)
- Stammdaten werden als Projektvariablen in QGIS hinterlegt
- Gewählte Layer werden direkt in das aktuelle `QgsProject` übernommen (Button: **Dem Projekt hinzufügen**)
- Nach dem Hinzufügen wird die Auswahl im Tree automatisch zurückgesetzt, um Doppelimporte zu vermeiden
- Importierte Layer werden in Projektgruppen abgelegt (Gruppenname aus JSON-Definition)
- Je Layer kann optional eine QML-Styledatei mitgeliefert werden (`qml` oder `style_qml` im Katalog)
- Virtuelle Layer (`source_type: "virtual"`) sind im Katalog möglich, inkl. SQL (`sql`) und Abhängigkeiten (`dependencies`)
- PostgreSQL/PostGIS-Layer (`source_type: "postgres"`) werden unterstützt
- SQLite/SpatiaLite-Layer (`source_type: "sqlite"` oder `"spatialite"`) werden unterstützt (auch SQLite-Tabellen ohne Geometrie)
- MBTiles-Raster (`source_type: "mbtiles"`) werden unterstützt
- Ohne expliziten Eintrag wird automatisch eine gleichnamige `.qml` zur Layerquelle gesucht (auch bei UNC-Pfaden)
- Offline-Funktion:
  - Kopiert **nur dateibasierte Quellen** (z. B. SHP/GPKG) in einen Cache
  - Überspringt Webdienste (WMS/WFS/XYZ)
- Optional kann je Layer `"allow_offline_copy": false` gesetzt werden, um das Kopieren gezielt zu verhindern

## Katalog-Update über Plugin

- PostgreSQL/PostGIS nutzt QGIS-Authentifizierung über `authname` im Katalog (festen Authentifizierungsnamen aus **QGIS > Einstellungen > Authentifizierung**).
- Pfade zur Server-Katalogdatei kommen aus `settings.json` und können per Upload im Plugin aktualisiert werden.
- Der Anwender kann über **"Katalog aktualisieren"** den lokalen Katalog gezielt vom Netzwerklaufwerk aktualisieren.
- Damit bleibt der Katalog einzeln updatebar, ohne das Plugin selbst neu zu installieren.

## Visueller Update-Hinweis für Layer

- Jeder Layer kann im Katalog eine `id` und `version` enthalten.
- Das Plugin vergleicht lokalen und Server-Katalog.
- Ist ein Layer auf dem Server neuer, wird er im Layer-Reiter mit **"⚠ Server neuer"** markiert (rot hervorgehoben).

## Katalogmodell (Admin-freundlich)

Die Layer- und Layoutverwaltung ist in JSON-Dateien gehalten.

- Default-Template: `bo_projektstart/default_catalog.json`
- Ausführliche JSON-Pflegedokumentation: `docs/catalog_json.md`
- Hilfsdatei zum Codieren/Decodieren von `settings.json`: `docs/settings_codec_helper.html`
- Lokale aktive Kopie: `bo_projektstart/local_catalog.json`
- Zentraler Katalogpfad ist im Plugin fest hinterlegt und unterstützt Laufwerks- und UNC-Pfade (z. B. `W:/Karten/1234/catalog.json` oder `\\vfgis\Karten\1234\catalog.json`).

Damit kann eine einfache Admin-Verwaltung ohne separates Admin-Plugin erfolgen: JSON-Datei pflegen, Version erhöhen, Anwender aktualisieren den Katalog im Plugin.

## Installation in QGIS

### Plugin installieren

#### Manuell

1. Repository nach `<QGIS-Profil>/python/plugins/` kopieren.
2. Ordnername: `bo_projektstart`.
3. QGIS neu starten.
4. Plugin in **Erweiterungen** aktivieren.
5. Menüeintrag **Bo-Projektstart** öffnen.

#### Über QGIS

1. Zip Datei herunterladen
2. Zip Datei unter der QGIS Erweiterungsverwaltung als manuelles Plugin installieren

### Einrichtung

Die Settings.json Datei im Plugin einlesen. 
## Virtuelle Layer im Katalog

- `source_type: "virtual"` aktiviert die Erstellung als virtueller Layer.
- SQL-Abfrage wird im Feld `sql` gespeichert.
- Referenzlayer werden über `dependencies` (Liste von Layer-IDs) angegeben.
- Optional können SQL-Quellnamen über `dependency_aliases` gesteuert werden.


## PostgreSQL/PostGIS im Katalog

- Setze `source_type: "postgres"` (alternativ `postgis`/`postgresql`).
- Verwendete Felder: `host`, `port`, `database`, `schema`, `table`, `geometry_column`, `key_column`, optional `where`.
- Hinterlege im Layer stattdessen `authname` mit dem QGIS-Authentifizierungsnamen (z. B. `"authname": "projektstart_pg"`).


## Layout-Variablen (Stammdaten im Layout nutzen)

Das Plugin schreibt folgende Projektvariablen beim Hinzufügen in das Projekt:

- `user_firstname`
- `user_lastname`
- `user_phone`
- `user_mail`
- `user_department`

Beispiele im Layout (Textfeld-Ausdruck):

- `[% @user_firstname %] [% @user_lastname %]`
- `[% @user_department %]`
- `[% @user_mail %]`

Die Variablen können auch im Projekt über **Projekt > Eigenschaften > Variablen** geprüft werden.
