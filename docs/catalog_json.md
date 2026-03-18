# Dokumentation Katalog-JSON (`catalog.json`)

Diese Datei beschreibt, wie die Katalogdatei für das Plugin **Bo-Projektstart** gepflegt werden muss.

## 1) Grundstruktur

```json
{
  "version": "1.2.0",
  "layer_categories": [
    {
      "name": "Kategorie",
      "groups": [
        {
          "name": "Gruppe",
          "layers": []
        }
      ]
    }
  ],
  "layouts": [
    {
      "name": "Layout A4",
      "path": "W:/Karten/1234/layouts/layout_a4.qpt"
    }
  ]
}
```

## 2) Top-Level Felder

- `version` *(String)*: Katalogversion für Update-Hinweise.
- `layer_categories` *(Array)*: Kategorien mit Gruppen und Layern.
- `layouts` *(Array)*: Layoutvorlagen (`.qpt`) mit Anzeige von Name + Beschreibung im Plugin.

## 3) Kategorien und Gruppen

Jeder Layer liegt in:

- **Kategorie** (`layer_categories[].name`)
- **Gruppe** (`layer_categories[].groups[].name`)

Die Gruppe wird beim Import als Gruppenname im QGIS-Projekt verwendet.

## 4) Gemeinsame Layer-Felder

Diese Felder sind für praktisch alle Layer sinnvoll:

- `id` *(String, empfohlen eindeutig)*
- `name` *(String)*
- `description` *(String, Kurzbeschreibung für UI)*
- `version` *(String, z. B. `"1.0.0"`)*
- `source_type` *(String)*

Optional für Styling:

- `qml` *(String Pfad)* oder
- `style_qml` *(String Pfad)*

Optional für Offline-Export:

- `allow_offline_copy` *(Boolean, Standard: `true`)* – Wenn `false`, wird der Layer beim Button **Offline-Paket erzeugen** bewusst nicht kopiert.

Wenn kein `qml/style_qml` gesetzt ist, versucht das Plugin automatisch eine gleichnamige `.qml` zur Layerquelle.

## 5) Layer-Typen (`source_type`)

## 5.1 Dateibasiert (SHP/GPKG/Raster)

```json
{
  "id": "projekt_a_layer_b",
  "name": "Layer B",
  "description": "Flurstücke",
  "version": "1.0.0",
  "source_type": "shp",
  "source": "W:/Karten/1234/projekt_a/layer_b.shp"
}
```

Hinweis: `source_type` kann hier auch z. B. `geopackage` sein; geladen wird als OGR (mit Raster-Fallback).

Wenn ein dateibasierter Layer **nicht** ins Offline-Paket übernommen werden darf, ergänze:

```json
"allow_offline_copy": false
```

## 5.2 Webdienste (WMS/WFS/XYZ)

```json
{
  "id": "luftbild_2025",
  "name": "Luftbild 2025",
  "description": "Orthofoto",
  "version": "1.0.0",
  "source_type": "wms",
  "source": "https://.../wms?..."
}
```

Mögliche Typen:

- `wms`
- `wfs`
- `xyz` / `tiles`

## 5.3 PostgreSQL / PostGIS

```json
{
  "id": "projekt_a_postgres_flaechen",
  "name": "Flächen (PostGIS)",
  "description": "Fachdaten aus PostGIS",
  "version": "1.0.0",
  "source_type": "postgres",
  "host": "dbserver.intern",
  "port": "5432",
  "database": "gis",
  "schema": "public",
  "table": "projekt_flaechen",
  "geometry_column": "geom",
  "key_column": "id",
  "where": "projekt_id = 1234",
  "authname": "projektstart_pg"
}
```

Alternativ kann ein fertiges `uri`-Feld verwendet werden.

**Wichtig:** Die Anmeldung läuft über QGIS-Authentifizierung. Trage im Katalog `authname` mit dem festen Authentifizierungsnamen aus QGIS ein.

## 5.4 SQLite / SpatiaLite

SQLite-Quellen können mit und ohne Geometrie eingebunden werden. Das Plugin unterstützt dafür
`source_type: "sqlite"` und `source_type: "spatialite"`.

### 5.4.1 Geometrischer SQLite/SpatiaLite-Layer (empfohlenes Schema)

```json
{
  "id": "projekt_a_sqlite_flaechen",
  "name": "Flächen (SQLite)",
  "description": "Lokaler SQLite/SpatiaLite-Layer",
  "version": "1.0.0",
  "source_type": "sqlite",
  "source": "W:/Karten/1234/projekt_a/fachdaten.sqlite",
  "table": "flaechen",
  "geometry_column": "geom",
  "key_column": "id",
  "where": "status = 'aktiv'"
}
```

**Bedeutung der Felder:**

- `source`: Dateipfad zur SQLite-/SpatiaLite-Datei (`.sqlite`, `.db`, ggf. `.gpkg`).
- `table`: Tabellenname innerhalb der Datenbank.
- `geometry_column`: Name der Geometriespalte (z. B. `geom`).
- `key_column`: Eindeutiger Schlüssel (optional, aber empfohlen).
- `where`: Optionaler Filter (SQL-`WHERE`-Ausdruck ohne das Wort `WHERE`).

### 5.4.2 SQLite-Tabelle ohne Geometrie (Attributtabelle)

Für reine Attributtabellen `geometry_column` **weglassen**:

```json
{
  "id": "projekt_a_sqlite_tabelle",
  "name": "Sachstand",
  "description": "Attributtabelle ohne Geometrie",
  "version": "1.0.0",
  "source_type": "sqlite",
  "source": "W:/Karten/1234/projekt_a/fachdaten.sqlite",
  "table": "sachstand"
}
```

Das Plugin versucht in diesem Fall den Import als OGR-Tabellenlayer über
`source|layername=<table>`.

### 5.4.3 Alternative mit vollständiger URI

Statt einzelner Felder kann direkt `uri` gesetzt werden:

```json
{
  "id": "projekt_a_sqlite_uri",
  "name": "Flächen (URI)",
  "version": "1.0.0",
  "source_type": "spatialite",
  "uri": "dbname='W:/Karten/1234/projekt_a/fachdaten.sqlite' table=\"flaechen\" (geom) key='id'"
}
```

### 5.4.4 Lade-Logik im Plugin (wichtig für Fehlersuche)

Das Plugin lädt SQLite in dieser Reihenfolge:

1. Bei `table` ohne `geometry_column`: zuerst OGR (`source|layername=...`).
2. Danach Versuch über Spatialite-Provider mit URI.
3. Falls nötig OGR-Fallbacks.

Dadurch funktionieren sowohl geometrische als auch nicht-geometrische SQLite-Quellen robuster.

### 5.4.5 Typen und Praxis-Hinweise

Mögliche Typen:

- `sqlite`
- `spatialite`

Empfehlungen:

- Pfade stabil halten und mit `/` oder korrekt escaped `\` schreiben.
- `table` exakt wie in der DB benennen (Groß-/Kleinschreibung beachten).
- Bei Fehlern zuerst prüfen: Datei erreichbar, Tabelle vorhanden, ggf. Geometriespalte korrekt benannt.

## 5.5 MBTiles

MBTiles-Raster können direkt eingebunden werden. Verwende dafür `source_type: "mbtiles"` und den Dateipfad als `source`:

```json
{
  "id": "hintergrund_mbtiles",
  "name": "Hintergrund (MBTiles)",
  "description": "Lokaler Raster-Kachelhintergrund",
  "version": "1.0.0",
  "source_type": "mbtiles",
  "source": "W:/Karten/1234/hintergrund.mbtiles"
}
```

Hinweise:

- MBTiles wird als Raster über den GDAL-Provider geladen.
- Für Offline-Pakete ist MBTiles dateibasiert und wird daher mitkopiert (sofern die Datei erreichbar ist).

## 5.5 Virtuelle Layer

```json
{
  "id": "projekt_a_labels_virtual",
  "name": "Beschriftung (virtuell)",
  "description": "Beschriftungs-Layer",
  "version": "1.0.0",
  "source_type": "virtual",
  "sql": "SELECT fid, geometry, name FROM projekt_a_layer_a",
  "dependencies": ["projekt_a_layer_a"],
  "dependency_aliases": {
    "projekt_a_layer_a": "projekt_a_layer_a"
  }
}
```

- `sql` enthält die SQL-Abfrage.
- `dependencies` enthält die referenzierten Layer-IDs.
- `dependency_aliases` ist optional für Aliasnamen in SQL.

## 6) Layouts

Der Pfad (`path`) bleibt im Katalog erforderlich, wird aber in der Plugin-Oberfläche nicht angezeigt.
Stattdessen wird die `description` angezeigt.

```json
{
  "name": "Layout A3",
  "description": "Drucklayout für Übersichtsplan",
  "path": "W:/Karten/1234/layouts/layout_a3.qpt"
}
```

## 7) Pflege-Regeln (Empfehlung)

1. `id` immer eindeutig halten.
2. Bei Datenänderung `version` erhöhen.
3. Bei strukturellen Änderungen auch Top-Level `version` erhöhen.
4. Pfade auf dem Netzlaufwerk stabil halten.
5. Für virtuelle Layer zuerst sicherstellen, dass alle `dependencies` im selben Katalog vorhanden sind.

## 8) Minimales vollständiges Beispiel

Siehe auch: `bo_projektstart/default_catalog.json`.


## 9) Laufwerks- und UNC-Pfade

Das Plugin unterstützt sowohl klassische Laufwerksangaben als auch UNC-Netzwerkpfade.

Beispiele:

- Laufwerk: `W:/Karten/1234/projekt_a/layer_a.gpkg`
- UNC: `\\vfgis\Karten\1234\projekt_a\layer_a.gpkg`

Wichtig für JSON: Backslashes müssen escaped werden (also `\\` statt `\`).

Das gilt für `source`, `qml/style_qml` und zentrale Katalogpfade gleichermaßen.


## 10) Server-Settings (Upload im UI)

Serverbezogene Pfade werden in `bo_projektstart/settings.json` gepflegt, z. B. Server-Katalogkandidaten und Standard-Cache.
Diese Datei kann im Plugin über den Button **"Settings.json laden"** aktualisiert werden.

Lokale Benutzer-/Systemdaten (Cache-Pfad und Stammdaten) werden separat in `bo_projektstart/user_profile.json` gespeichert.
Mit dem `settings_codec_helper.html` Skript können die Informationen der Settings.json noch mittels Base64 und XOR unleserlich gemacht werden.
Dies ist keine Verschlüsselung!

## 11) Stammdaten als Projekt-/Layout-Variablen

Aus den Einstellungen werden folgende Projektvariablen gesetzt:

- `user_firstname`
- `user_lastname`
- `user_phone`
- `user_mail`
- `user_department`

Verwendung im Layout-Text (Ausdruck): `[% @user_firstname %] [% @user_lastname %]`
