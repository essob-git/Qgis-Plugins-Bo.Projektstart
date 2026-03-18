"""QGIS plugin to bootstrap projects from a managed layer/layout catalog."""

from __future__ import annotations

import configparser
import base64
import json
import ntpath
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsApplication,
    QgsAuthMethodConfig,
    QgsDataSourceUri,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsVectorLayer,
    QgsVirtualLayerDefinition,
)
from qgis.PyQt.QtWidgets import (
    QAction,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def tr(message: str) -> str:
    return QCoreApplication.translate("BoProjektstartPlugin", message)


class PluginDialog(QDialog):
    """Main plugin dialog with tabs for layers, layouts, settings and credits."""

    def __init__(self, plugin: "BoProjektstartPlugin"):
        super().__init__(plugin.iface.mainWindow())
        self.plugin = plugin
        self.setWindowTitle(tr("Bo-Projektstart - Musterprojekt erstellen"))
        self.resize(1024, 640)

        self.tabs = QTabWidget()
        self.layer_tree = QTreeWidget()
        self.layout_tree = QTreeWidget()
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

        self.tabs.addTab(self._build_layers_tab(), tr("Layer"))
        self.tabs.addTab(self._build_layout_tab(), tr("Layouts"))
        self.tabs.addTab(self._build_settings_tab(), tr("Einstellungen"))
        self.tabs.addTab(self._build_credits_tab(), tr("Credits"))

        footer = QHBoxLayout()
        footer.addStretch(1)

        self.btn_check_updates = QPushButton(tr("Updates prüfen"))
        self.btn_check_updates.clicked.connect(self._check_updates_and_refresh)
        footer.addWidget(self.btn_check_updates)

        self.btn_update_catalog = QPushButton(tr("Katalog aktualisieren"))
        self.btn_update_catalog.clicked.connect(self._update_catalog_and_refresh)
        footer.addWidget(self.btn_update_catalog)

        self.btn_copy_offline = QPushButton(tr("Offline-Paket erzeugen"))
        self.btn_copy_offline.clicked.connect(self.plugin.export_offline_package)
        footer.addWidget(self.btn_copy_offline)

        self.btn_create_project = QPushButton(tr("Dem Projekt hinzufügen"))
        self.btn_create_project.clicked.connect(self._create_project)
        footer.addWidget(self.btn_create_project)

        root.addLayout(footer)

    def _build_layers_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        info = QLabel(
            tr(
                "Wählen Sie die Layer, die ins Projekt übernommen werden sollen. "
                "Kategorien sind mindestens zweistufig aufgebaut. "
                "Status zeigt, ob auf dem Server eine neuere Layer-Version vorliegt."
            )
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.layer_tree.setHeaderLabels([tr("Layer"), tr("Kurzbeschreibung"), tr("Typ"), tr("Status"), tr("Visualisierung")])
        self.layer_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.layer_tree.setStyleSheet(
            "QTreeWidget::item:selected { background: transparent; color: inherit; }"
            "QTreeWidget::item:hover { background: rgba(31, 78, 121, 0.10); }"
        )

        self.layer_tree.setColumnWidth(0, 260)
        self.layer_tree.setColumnWidth(1, 340)
        self.layer_tree.setColumnWidth(2, 90)
        self.layer_tree.setColumnWidth(3, 90)
        self.layer_tree.setColumnWidth(4, 180)
        layout.addWidget(self.layer_tree)

        return page

    def _build_layout_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        info = QLabel(
            tr("Verfügbare Layoutvorlagen vom Netzlaufwerk. Gewählte Layouts werden ins Projekt eingebunden.")
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.layout_tree.setHeaderLabels([tr("Layout"), tr("Beschreibung")])
        self.layout_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.layout_tree.setStyleSheet(
            "QTreeWidget::item:selected { background: transparent; color: inherit; }"
            "QTreeWidget::item:hover { background: rgba(31, 78, 121, 0.10); }"
        )
        self.layout_tree.setColumnWidth(0, 260)
        self.layout_tree.setColumnWidth(1, 360)
        layout.addWidget(self.layout_tree)

        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        
        info = QLabel(
            tr("Userdaten, diese werden nach dem Import eines Layers / Layouts in Projekt geschrieben.")
        )
       
        

    
        user_box = QGroupBox(tr("Stammdaten"))
        user_form = QFormLayout(user_box)

        self.input_firstname = QLineEdit()
        self.input_lastname = QLineEdit()
        self.input_phone = QLineEdit()
        self.input_mail = QLineEdit()
        self.input_department = QLineEdit()

        user_form.addRow(tr("Vorname"), self.input_firstname)
        user_form.addRow(tr("Nachname"), self.input_lastname)
        user_form.addRow(tr("Telefon"), self.input_phone)
        user_form.addRow(tr("E-Mail"), self.input_mail)
        user_form.addRow(tr("Abteilung"), self.input_department)

        system_box = QGroupBox(tr("Plugin-Einstellungen"))
        system_form = QFormLayout(system_box)

        self.input_cache_dir = QLineEdit()
        self.input_cache_dir.setPlaceholderText(self.plugin.default_cache_dir)
        system_form.addRow(tr("Offline-Cache"), self.input_cache_dir)

        layout.addWidget(info)
        layout.addWidget(user_box)
        layout.addWidget(system_box)

        row = QHBoxLayout()
        import_btn = QPushButton(tr("Settings.json laden"))
        import_btn.clicked.connect(self._import_server_settings)
        row.addWidget(import_btn)

        row.addStretch(1)
        save_btn = QPushButton(tr("Einstellungen speichern"))
        save_btn.clicked.connect(self._save_settings)
        row.addWidget(save_btn)
        layout.addLayout(row)

        return page

    def _build_credits_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        meta = self.plugin.metadata
        html = (
            "<div style='font-family:Segoe UI,Arial,sans-serif; padding:12px;'>"
            "<h2 style='margin:0 0 10px 0;'>Bo-Projektstart Plugin</h2>"
            "<p style='margin:0 0 14px 0; color:#555;'>Musterprojekt-Generator für QGIS</p>"
            "<table style='border-collapse:collapse;'>"
            f"<tr><td style='padding:4px 10px 4px 0;'><b>Version</b></td><td style='padding:4px 10px 4px 0;'>{meta.get('version','-')}</td></tr>"
            f"<tr><td style='padding:4px 10px 4px 0;'><b>Ersteller</b></td><td style='padding:4px 10px 4px 0;'>{meta.get('author','-')}</td></tr>"
            f"<tr><td style='padding:4px 10px 4px 0;'><b>E-Mail</b></td><td style='padding:4px 10px 4px 0;'>{meta.get('email','-')}</td></tr>"
            f"<tr><td style='padding:4px 10px 4px 0;'><b>Beschreibung</b></td><td style='padding:4px 10px 4px 0;'>{meta.get('about','-')}</td></tr>"
            "</table>"
            "</div>"
        )

        info = QLabel(html)
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        layout.addWidget(info)
        layout.addStretch(1)
        return page

    def _load_data(self) -> None:
        self.plugin.load_catalog()
        self._populate_layer_tree()
        self._populate_layout_tree()

        settings = self.plugin.settings
        self.input_firstname.setText(settings.get("firstname", ""))
        self.input_lastname.setText(settings.get("lastname", ""))
        self.input_phone.setText(settings.get("phone", ""))
        self.input_mail.setText(settings.get("mail", ""))
        self.input_department.setText(settings.get("department", ""))
        self.input_cache_dir.setText(settings.get("cache_dir", ""))

    def _populate_layer_tree(self) -> None:
        self.layer_tree.clear()
        outdated_keys = self.plugin.outdated_layer_keys

        for category in self.plugin.catalog.get("layer_categories", []):
            category_item = QTreeWidgetItem([category.get("name", ""), "", "", "", ""])
            category_item.setFlags(category_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            category_font = QFont(category_item.font(0))
            category_font.setBold(True)
            for col in range(4):
                category_item.setFont(col, category_font)
                category_item.setForeground(col, QColor("#1f4e79"))
            self.layer_tree.addTopLevelItem(category_item)

            for subgroup in category.get("groups", []):
                group_item = QTreeWidgetItem([subgroup.get("name", ""), "", "", "", ""])
                group_item.setFlags(group_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                category_item.addChild(group_item)

                for layer in subgroup.get("layers", []):
                    layer_key = self.plugin.layer_key(layer)
                    is_outdated = layer_key in outdated_keys
                    status = tr("⚠ Server neuer") if is_outdated else tr("Aktuell")
                    layer_item = QTreeWidgetItem([
                        layer.get("name", ""),
                        layer.get("description", ""),
                        layer.get("source_type", ""),
                        status,
                        "",
                    ])
                    layer_payload = dict(layer)
                    layer_payload["__group_name"] = subgroup.get("name", "")
                    layer_item.setData(0, Qt.UserRole, layer_payload)
                    layer_item.setFlags(layer_item.flags() | Qt.ItemIsUserCheckable)
                    layer_item.setCheckState(0, Qt.Unchecked)

                    source_type = str(layer.get("source_type", "")).lower()
                    style_combo: Optional[QComboBox] = None
                    if source_type != "wms":
                        style_combo = QComboBox(self.layer_tree)
                        style_combo.addItem(tr("standard"), "__standard__")
                        for style_option in self.plugin.collect_qml_style_options(layer):
                            style_combo.addItem(style_option["label"], style_option["qml"])

                    if is_outdated:
                        for col in range(5):
                            layer_item.setForeground(col, QColor("#b00020"))
                    group_item.addChild(layer_item)
                    if style_combo is not None:
                        self.layer_tree.setItemWidget(layer_item, 4, style_combo)

        self.layer_tree.expandAll()

    def _populate_layout_tree(self) -> None:
        self.layout_tree.clear()
        for layout in self.plugin.catalog.get("layouts", []):
            item = QTreeWidgetItem([layout.get("name", "Layout"), layout.get("description", "")])
            item.setData(0, Qt.UserRole, layout)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            self.layout_tree.addTopLevelItem(item)

    def _import_server_settings(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            tr("Settings-Datei auswählen"),
            str(Path.home()),
            tr("Settings-Dateien (*.json *.txt);;Alle Dateien (*)"),
        )
        if not selected:
            return

        source = self.plugin._decode_uploaded_settings(Path(selected))
        if not source:
            QMessageBox.warning(
                self,
                tr("Ungültige Settings-Datei"),
                tr(
                    "Die Datei muss gültige Plugin-Settings enthalten. "
                    "Unterstützt werden Klartext-JSON oder ein verschlüsselter Payload."
                ),
            )
            return

        self.plugin._write_json(self.plugin.settings_path, source)
        self.plugin.reload_server_settings()
        self.input_cache_dir.setPlaceholderText(self.plugin.default_cache_dir)
        QMessageBox.information(self, tr("Import erfolgreich"), tr("Server-Settings wurden übernommen."))

    def _checked_layers(self) -> List[Dict]:
        layers: List[Dict] = []

        def walk(item: QTreeWidgetItem) -> None:
            for idx in range(item.childCount()):
                child = item.child(idx)
                data = child.data(0, Qt.UserRole)
                if data and child.checkState(0) == Qt.Checked:
                    layer_payload = dict(data)
                    style_widget = self.layer_tree.itemWidget(child, 4)
                    if isinstance(style_widget, QComboBox):
                        layer_payload["__selected_qml"] = str(style_widget.currentData() or "__standard__")
                    layers.append(layer_payload)
                walk(child)

        for i in range(self.layer_tree.topLevelItemCount()):
            walk(self.layer_tree.topLevelItem(i))
        return layers

    def _checked_layouts(self) -> List[Dict]:
        layouts: List[Dict] = []
        for i in range(self.layout_tree.topLevelItemCount()):
            item = self.layout_tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                layouts.append(item.data(0, Qt.UserRole))
        return layouts

    def _save_settings(self, show_message: bool = True) -> None:
        self.plugin.settings.update(
            {
                "firstname": self.input_firstname.text().strip(),
                "lastname": self.input_lastname.text().strip(),
                "phone": self.input_phone.text().strip(),
                "mail": self.input_mail.text().strip(),
                "department": self.input_department.text().strip(),
                "cache_dir": self.input_cache_dir.text().strip(),
            }
        )
        self.plugin.save_settings()
        if show_message:
            QMessageBox.information(self, tr("Gespeichert"), tr("Einstellungen wurden gespeichert."))

    def _check_updates_and_refresh(self) -> None:
        self._save_settings(show_message=False)
        self.plugin.check_for_updates()
        self.plugin.load_catalog()
        self._populate_layer_tree()
        self._populate_layout_tree()

    def _update_catalog_and_refresh(self) -> None:
        self._save_settings(show_message=False)
        if self.plugin.update_local_catalog_from_server():
            self.plugin.load_catalog()
            self._populate_layer_tree()
            self._populate_layout_tree()

    def _create_project(self) -> None:
        selected_layers = self._checked_layers()
        selected_layouts = self._checked_layouts()

        if not selected_layers and not selected_layouts:
            QMessageBox.warning(self, tr("Keine Auswahl"), tr("Bitte mindestens einen Layer oder ein Layout auswählen."))
            return

        self._save_settings(show_message=False)
        self.plugin.create_project(selected_layers, selected_layouts)
        self._clear_selections()

    def _clear_selections(self) -> None:
        def uncheck_tree(item: QTreeWidgetItem) -> None:
            for idx in range(item.childCount()):
                child = item.child(idx)
                child.setCheckState(0, Qt.Unchecked)
                uncheck_tree(child)

        for i in range(self.layer_tree.topLevelItemCount()):
            root = self.layer_tree.topLevelItem(i)
            root.setCheckState(0, Qt.Unchecked)
            uncheck_tree(root)

        for i in range(self.layout_tree.topLevelItemCount()):
            item = self.layout_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)



class BoProjektstartPlugin:
    """Main plugin entrypoint."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self.action: Optional[QAction] = None
        self.dialog: Optional[PluginDialog] = None
        self.catalog: Dict = {}
        self.server_catalog: Dict = {}
        self.outdated_layer_keys: Set[str] = set()
        self.active_server_catalog_paths: Dict[str, Path] = {}
        self.server_catalog_candidates: List[Path] = [
            Path("W:/Karten/1234/catalog.json"),
            Path(r"\\vfgis\Karten\1234\catalog.json"),
        ]
        self.active_server_catalog_path: Optional[Path] = None

        self.settings_path = self.plugin_dir / "settings.json"
        self.user_profile_path = self.plugin_dir / "user_profile.json"
        self.legacy_config_path = self.plugin_dir / "plugin_config.json"
        self.default_catalog_path = self.plugin_dir / "default_catalog.json"
        self.local_catalog_path = self.plugin_dir / "local_catalog.json"
        self._migrate_legacy_settings()
        self.settings = self._read_json(self.user_profile_path) or {}
        self.server_settings = self._load_server_settings()
        self.server_catalog_candidates = [Path(p) for p in self.server_settings.get("server_catalog_candidates", [])]
        
        self.default_cache_dir = self._resolve_cache_dir(
            self.server_settings.get("default_cache_dir", str(Path.home() / "QGISBoProjektstartCache"))
        )
        self.metadata = self._read_metadata()

    def initGui(self) -> None:
        if self.action is not None:
            return
        self.action = QAction(tr("Bo-Projektstart"), self.iface.mainWindow())
        self.action.triggered.connect(self.show_dialog)
        self.iface.addPluginToMenu(tr("Bo-Projektstart"), self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self) -> None:
        if self.action:
            self.iface.removePluginMenu(tr("Bo-Projektstart"), self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def show_dialog(self) -> None:
        self.dialog = PluginDialog(self)
        self.dialog.show()

    def _read_json(self, path: Path) -> Optional[Dict]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _decode_uploaded_settings(self, path: Path) -> Optional[Dict]:
        try:
            raw_content = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

        if not raw_content:
            return None

        decoded = self._decode_settings_payload(raw_content)
        if decoded and self._has_catalog_source_config(decoded):
            return decoded
        return None

    def _decode_settings_payload(self, payload: str) -> Optional[Dict]:
        # 1) Direktes JSON unterstützen (Rückwärtskompatibilität)
        try:
            plain = json.loads(payload)
        except json.JSONDecodeError:
            plain = None

        if isinstance(plain, dict):
            if self._has_catalog_source_config(plain):
                return plain

            encrypted_blob = plain.get("encrypted_settings")
            if isinstance(encrypted_blob, str):
                return self._decrypt_settings_blob(encrypted_blob)

        # 2) Reinen Blob-Text als Dateiformat zulassen
        return self._decrypt_settings_blob(payload)

    def _decrypt_settings_blob(self, blob: str) -> Optional[Dict]:
        key = "BoProjektstartSettingsV1"
        try:
            encrypted_bytes = base64.b64decode(blob.encode("utf-8"), validate=True)
        except (ValueError, OSError):
            return None

        if not encrypted_bytes:
            return None

        decrypted = bytes(
            value ^ ord(key[index % len(key)])
            for index, value in enumerate(encrypted_bytes)
        )

        try:
            payload = json.loads(decrypted.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_json(self, path: Path, payload: Dict) -> None:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    def _expand_env_placeholders(self, value: str) -> str:
        if not value:
            return value

        environment = dict(os.environ)
        environment.update({key.upper(): val for key, val in os.environ.items()})
        environment.update({key.lower(): val for key, val in os.environ.items()})

        def replace_percent_token(match: re.Match[str]) -> str:
            token = match.group(1)
            return environment.get(token, environment.get(token.upper(), environment.get(token.lower(), match.group(0))))

        expanded = re.sub(r"%([^%]+)%", replace_percent_token, value)
        expanded = os.path.expandvars(expanded)
        return os.path.expanduser(expanded)

    def _resolve_cache_dir(self, value: object) -> str:
        configured = str(value or Path.home() / "QGISBoProjektstartCache")
        return self._expand_env_placeholders(configured)

    def _is_absolute_catalog_path(self, raw_path: str) -> bool:
        path_value = str(raw_path).strip()
        if not path_value:
            return False
        return Path(path_value).is_absolute() or ntpath.isabs(path_value)

    def _join_catalog_path(self, base_path: str, relative_path: str) -> str:
        base_value = str(base_path).strip()
        relative_value = str(relative_path).strip()
        if not base_value:
            return relative_value
        if not relative_value or self._is_absolute_catalog_path(relative_value):
            return relative_value

        if ntpath.isabs(base_value) or "\\" in base_value:
            return ntpath.normpath(ntpath.join(base_value, relative_value))
        return str(Path(base_value) / relative_value)

    def _has_catalog_source_config(self, payload: Dict) -> bool:
        return isinstance(payload.get("server_catalog_candidates"), list) or isinstance(payload.get("catalog_sources"), list)

    def _catalog_sources_from_settings(self) -> List[Dict]:
        configured_sources = self.server_settings.get("catalog_sources")
        if isinstance(configured_sources, list):
            normalized_sources: List[Dict] = []
            for idx, raw_source in enumerate(configured_sources):
                if isinstance(raw_source, str):
                    normalized_sources.append(
                        {
                            "id": f"catalog_{idx + 1}",
                            "label": f"Katalog {idx + 1}",
                            "enabled": True,
                            "candidates": [raw_source],
                        }
                    )
                    continue

                if not isinstance(raw_source, dict):
                    continue

                candidates = raw_source.get("candidates")
                if not isinstance(candidates, list):
                    single_path = raw_source.get("path")
                    candidates = [single_path] if single_path else []

                normalized_candidates = [str(candidate).strip() for candidate in candidates if str(candidate).strip()]
                if not normalized_candidates:
                    continue

                normalized_sources.append(
                    {
                        "id": str(raw_source.get("id") or f"catalog_{idx + 1}"),
                        "label": str(raw_source.get("label") or raw_source.get("name") or f"Katalog {idx + 1}"),
                        "enabled": bool(raw_source.get("enabled", True)),
                        "candidates": normalized_candidates,
                    }
                )
            if normalized_sources:
                return normalized_sources

        legacy_candidates = self.server_settings.get("server_catalog_candidates", []) or []
        if isinstance(legacy_candidates, list) and legacy_candidates:
            return [
                {
                    "id": "global",
                    "label": "Global",
                    "enabled": True,
                    "candidates": [str(candidate).strip() for candidate in legacy_candidates if str(candidate).strip()],
                }
            ]
        return []

    def _server_catalog_path(self) -> Optional[Path]:
        if self.active_server_catalog_path and self.active_server_catalog_path.exists():
            return self.active_server_catalog_path

        for candidate in self.server_catalog_candidates:
            if candidate.exists():
                self.active_server_catalog_path = candidate
                return candidate

        # Fallback to first configured path (e.g. before network mount is available)
        return self.server_catalog_candidates[0] if self.server_catalog_candidates else None

    def _default_server_settings(self) -> Dict:
        return {
            "server_catalog_candidates": [
                "W:/Karten/1234/catalog.json",
                r"\\vfgis\Karten\1234\catalog.json",
            ],
            "catalog_sources": [
                {
                    "id": "global",
                    "label": "Global",
                    "enabled": True,
                    "candidates": [
                        "W:/Karten/1234/catalog.json",
                        r"\\vfgis\Karten\1234\catalog.json",
                    ],
                }
            ],
            "default_cache_dir": str(Path.home() / "QGISBoProjektstartCache"),
        }

    def _load_server_settings(self) -> Dict:
        cfg = self._read_json(self.settings_path)
        if not cfg:
            cfg = self._default_server_settings()
            self._write_json(self.settings_path, cfg)
            return cfg

        defaults = self._default_server_settings()
        defaults.update(cfg)
        if not isinstance(defaults.get("server_catalog_candidates"), list):
            defaults["server_catalog_candidates"] = self._default_server_settings()["server_catalog_candidates"]
        if not isinstance(defaults.get("catalog_sources"), list):
            defaults["catalog_sources"] = self._default_server_settings()["catalog_sources"]
        return defaults

    def reload_server_settings(self) -> None:
        self.server_settings = self._load_server_settings()
        self.server_catalog_candidates = [Path(p) for p in self.server_settings.get("server_catalog_candidates", [])]
        self.default_cache_dir = self._resolve_cache_dir(
            self.server_settings.get("default_cache_dir", str(Path.home() / "QGISBoProjektstartCache"))
        )
        self.active_server_catalog_path = None
        self.active_server_catalog_paths = {}

    def _migrate_legacy_settings(self) -> None:
        legacy_settings = self._read_json(self.settings_path) if self.settings_path.exists() else None
        legacy_plugin_config = self._read_json(self.legacy_config_path) if self.legacy_config_path.exists() else None

        is_legacy_user_payload = bool(legacy_settings and any(
            key in legacy_settings for key in ["firstname", "lastname", "phone", "mail", "department", "cache_dir"]
        ))

        if is_legacy_user_payload and not self.user_profile_path.exists():
            self._write_json(self.user_profile_path, legacy_settings or {})

        if (not legacy_settings or is_legacy_user_payload) and legacy_plugin_config:
            self._write_json(self.settings_path, legacy_plugin_config)

        if not self.user_profile_path.exists():
            self._write_json(self.user_profile_path, {})

    def _read_metadata(self) -> Dict[str, str]:
        metadata_path = self.plugin_dir / "metadata.txt"
        parser = configparser.ConfigParser()
        if not metadata_path.exists():
            return {}
        try:
            parser.read(metadata_path, encoding="utf-8")
        except (OSError, configparser.Error):
            return {}
        if "general" not in parser:
            return {}
        general = parser["general"]
        return {
            "name": general.get("name", ""),
            "version": general.get("version", ""),
            "author": general.get("author", ""),
            "email": general.get("email", ""),
            "about": general.get("about", ""),
        }

    def _default_catalog_payload(self) -> Dict:
        return {"version": "1.0.0", "layer_categories": [], "layouts": []}

    def _normalize_catalog(self, catalog: Optional[Dict], source_path: Optional[Path] = None) -> Dict:
        payload = dict(catalog or {})
        source_root = str(source_path.parent) if source_path else ""
        source_ref = str(source_path) if source_path else ""

        # Backward compatibility: allow old top-level key "layers"
        categories = payload.get("layer_categories")
        if categories is None and isinstance(payload.get("layers"), list):
            categories = [
                {
                    "name": "Standard",
                    "groups": [{"name": "Allgemein", "layers": payload.get("layers", [])}],
                }
            ]

        normalized_categories: List[Dict] = []
        for category in categories or []:
            if not isinstance(category, dict):
                continue
            category_name = str(category.get("name", "Kategorie"))
            groups = category.get("groups")

            # Backward compatibility: category contains layers directly
            if groups is None and isinstance(category.get("layers"), list):
                groups = [{"name": "Allgemein", "layers": category.get("layers", [])}]

            normalized_groups: List[Dict] = []
            for group in groups or []:
                if not isinstance(group, dict):
                    continue
                group_name = str(group.get("name", "Gruppe"))
                normalized_layers: List[Dict] = []
                for layer in group.get("layers", []) or []:
                    if not isinstance(layer, dict):
                        continue
                    layer_payload = dict(layer)
                    layer_payload.setdefault("name", "Layer")
                    layer_payload.setdefault("description", "")
                    layer_payload.setdefault("version", "0")
                    layer_payload.setdefault("source_type", "")
                    if source_root:
                        layer_payload.setdefault("__catalog_root", source_root)
                    if source_ref:
                        layer_payload.setdefault("__catalog_source", source_ref)
                    normalized_layers.append(layer_payload)
                normalized_groups.append({"name": group_name, "layers": normalized_layers})

            normalized_categories.append({"name": category_name, "groups": normalized_groups})

        normalized_layouts: List[Dict] = []
        for layout in payload.get("layouts", []) or []:
            if not isinstance(layout, dict):
                continue
            normalized_layouts.append({
                "name": str(layout.get("name", "Layout")),
                "description": str(layout.get("description", "")),
                "path": str(layout.get("path", "")),
                "__catalog_root": source_root,
                "__catalog_source": source_ref,
            })

        return {
            "version": str(payload.get("version", "1.0.0")),
            "layer_categories": normalized_categories,
            "layouts": normalized_layouts,
            "_source": source_ref,
        }

    def _merge_catalogs(self, catalogs: Sequence[Dict]) -> Dict:
        merged = self._default_catalog_payload()
        categories_by_name: Dict[str, Dict[str, Dict]] = {}
        seen_layouts: Set[str] = set()
        version_parts: List[str] = []

        for catalog in catalogs:
            if not catalog:
                continue

            catalog_source = str(catalog.get("_source", "")).strip()
            catalog_version = str(catalog.get("version", "")).strip()
            if catalog_source:
                version_parts.append(f"{Path(catalog_source).name}:{catalog_version or '0'}")
            elif catalog_version:
                version_parts.append(catalog_version)

            for category in catalog.get("layer_categories", []):
                category_name = str(category.get("name", "Kategorie"))
                merged_groups = categories_by_name.setdefault(category_name, {})
                for group in category.get("groups", []):
                    group_name = str(group.get("name", "Gruppe"))
                    target_group = merged_groups.setdefault(group_name, {"name": group_name, "layers": []})
                    target_group["layers"].extend(dict(layer) for layer in group.get("layers", []) if isinstance(layer, dict))

            for layout in catalog.get("layouts", []):
                layout_key = self._layout_key(layout)
                if not layout_key or layout_key in seen_layouts:
                    continue
                seen_layouts.add(layout_key)
                merged["layouts"].append(dict(layout))

        merged["layer_categories"] = [
            {
                "name": category_name,
                "groups": list(groups.values()),
            }
            for category_name, groups in categories_by_name.items()
        ]
        merged["version"] = " + ".join(version_parts) if version_parts else "1.0.0"
        return merged

    def _layout_key(self, layout: Dict) -> str:
        return str(layout.get("path") or layout.get("name") or "")

    def _resolve_catalog_source_path(self, source_id: str, candidates: Sequence[str]) -> Optional[Path]:
        cached_path = self.active_server_catalog_paths.get(source_id)
        if cached_path and cached_path.exists():
            return cached_path

        candidate_paths = [
            Path(self._expand_env_placeholders(str(candidate).strip()))
            for candidate in candidates
            if str(candidate).strip()
        ]
        for candidate in candidate_paths:
            if candidate.exists():
                self.active_server_catalog_paths[source_id] = candidate
                if source_id == "global":
                    self.active_server_catalog_path = candidate
                return candidate

        if candidate_paths:
            fallback = candidate_paths[0]
            self.active_server_catalog_paths[source_id] = fallback
            if source_id == "global":
                self.active_server_catalog_path = fallback
            return fallback
        return None

    def _load_server_catalogs(self) -> List[Dict]:
        server_catalogs: List[Dict] = []
        for source in self._catalog_sources_from_settings():
            if not source.get("enabled", True):
                continue
            source_id = str(source.get("id") or "catalog")
            source_path = self._resolve_catalog_source_path(source_id, source.get("candidates", []))
            if not source_path or not source_path.exists():
                continue
            raw_catalog = self._read_json(source_path)
            if not raw_catalog:
                continue
            server_catalogs.append(self._normalize_catalog(raw_catalog, source_path))
        return server_catalogs

    def _ensure_local_catalog(self) -> None:
        if self.local_catalog_path.exists():
            return
        default_catalog = self._normalize_catalog(self._read_json(self.default_catalog_path), self.default_catalog_path)
        self._write_json(self.local_catalog_path, default_catalog)

    def load_catalog(self) -> None:
        self._ensure_local_catalog()
        self.catalog = self._normalize_catalog(
            self._read_json(self.local_catalog_path) or self._default_catalog_payload(),
            self.local_catalog_path,
        )
        self.catalog["_source"] = str(self.local_catalog_path)

        server_catalogs = self._load_server_catalogs()
        self.server_catalog = self._merge_catalogs(server_catalogs) if server_catalogs else {}
        self.outdated_layer_keys = self._collect_outdated_layer_keys(self.catalog, self.server_catalog)

    def save_settings(self) -> None:
        self._write_json(self.user_profile_path, self.settings)

    def layer_key(self, layer: Dict) -> str:
        return str(layer.get("id") or layer.get("source") or layer.get("name") or "")

    def _layer_version(self, layer: Dict) -> str:
        return str(layer.get("version", "0"))

    def _collect_layer_map(self, catalog: Dict) -> Dict[str, Dict]:
        result: Dict[str, Dict] = {}
        for category in catalog.get("layer_categories", []):
            for subgroup in category.get("groups", []):
                for layer in subgroup.get("layers", []):
                    key = self.layer_key(layer)
                    if key:
                        result[key] = layer
        return result

    def _collect_outdated_layer_keys(self, local_catalog: Dict, server_catalog: Dict) -> Set[str]:
        if not server_catalog:
            return set()
        local_map = self._collect_layer_map(local_catalog)
        server_map = self._collect_layer_map(server_catalog)
        outdated: Set[str] = set()
        for key, server_layer in server_map.items():
            local_layer = local_map.get(key)
            if local_layer and self._layer_version(server_layer) > self._layer_version(local_layer):
                outdated.add(key)
        return outdated

    def update_local_catalog_from_server(self) -> bool:
        server_catalogs = self._load_server_catalogs()
        if not server_catalogs:
            QMessageBox.warning(self.iface.mainWindow(), tr("Katalog-Update"), tr("Katalogdatei am Server nicht gefunden."))
            return False

        server_catalog = self._merge_catalogs(server_catalogs)
        if not server_catalog.get("layer_categories") and not server_catalog.get("layouts"):
            QMessageBox.warning(self.iface.mainWindow(), tr("Katalog-Update"), tr("Server-Katalog ist leer oder ungültig."))
            return False

        self._write_json(self.local_catalog_path, server_catalog)
        QMessageBox.information(
            self.iface.mainWindow(),
            tr("Katalog-Update"),
            tr("Lokaler Katalog wurde erfolgreich vom Server aktualisiert."),
        )
        return True

    def create_project(self, layers: List[Dict], layouts: List[Dict]) -> None:
        self._publish_user_variables()
        added_layers, failed_layers = self._add_layers_to_project(layers)
        added_layouts, failed_layouts = self._add_layouts_to_project(layouts)

        msg_parts = [
            "<h3>Layer:</h3>",
            f"Ausgewählte Layer: {len(layers)}",
            f"Erfolgreich hinzugefügt: {added_layers}",
            f"<b>Fehlgeschlagen Layer:</b> {failed_layers}",
            "",  # Leerzeile
            f"<h3>Layouts</h3>",
            f"Ausgewählte Layouts: {len(layouts)}",
            f"Layouts importiert: {added_layouts}",
            f"<b>Layout-Import fehlgeschlagen:</b> {failed_layouts}",
        ]
        
        msg = "<html><body>" + "<br>".join(msg_parts) + "</body></html>"
        
        QMessageBox.information(
            self.iface.mainWindow(), 
            tr("Bo-Projektstart - Ergebnis"), 
            msg
        )

    def _add_layouts_to_project(self, layouts: List[Dict]) -> tuple[int, int]:
        project = QgsProject.instance()
        manager = project.layoutManager()
        added = 0
        failed = 0

        for layout in layouts:
            template_path = self._resolve_layout_path(layout)
            if not template_path or not template_path.exists():
                failed += 1
                continue

            try:
                template_bytes = template_path.read_bytes()
            except OSError:
                failed += 1
                continue

            document = QDomDocument("layout_template")
            if not document.setContent(template_bytes):
                failed += 1
                continue

            layout_name = str(layout.get("name", "")).strip() or template_path.stem
            existing_layout = manager.layoutByName(layout_name)
            if existing_layout is not None:
                manager.removeLayout(existing_layout)

            print_layout = QgsPrintLayout(project)
            print_layout.initializeDefaults()
            print_layout.setName(layout_name)

            try:
                load_result = print_layout.loadFromTemplate(document, QgsReadWriteContext(), True)
            except TypeError:
                load_result = print_layout.loadFromTemplate(document, QgsReadWriteContext())
            except Exception:
                failed += 1
                continue

            if load_result is False:
                failed += 1
                continue
            if isinstance(load_result, tuple) and load_result and load_result[0] is False:
                failed += 1
                continue

            manager.addLayout(print_layout)
            added += 1

        return added, failed

    def _resolve_layout_path(self, layout: Dict) -> Optional[Path]:
        raw_path = str(layout.get("path", "")).strip()
        if not raw_path:
            return None

        if self._is_absolute_catalog_path(raw_path):
            return Path(raw_path)

        catalog_root = str(layout.get("__catalog_root", "")).strip()
        if catalog_root:
            return Path(self._join_catalog_path(catalog_root, raw_path))

        server_path = self._server_catalog_path()
        server_root = server_path.parent if server_path else None
        if server_root:
            return Path(self._join_catalog_path(str(server_root), raw_path))
        return Path(self._join_catalog_path(str(self.plugin_dir), raw_path))

    def _add_layers_to_project(self, layers: List[Dict]) -> tuple[int, int]:
        project = QgsProject.instance()
        added = 0
        failed = 0
        loaded_by_key: Dict[str, object] = {}
        pending_virtual: List[Dict] = []

        for layer in layers:
            source_type = str(layer.get("source_type", "")).lower()
            if source_type == "virtual":
                pending_virtual.append(layer)
                continue

            qgs_layer = self._create_non_virtual_layer(layer)
            if qgs_layer and qgs_layer.isValid():
                self._apply_qml_style(qgs_layer, layer)
                self._add_layer_to_named_group(project, qgs_layer, layer)
                key = self.layer_key(layer)
                if key:
                    qgs_layer.setCustomProperty("projektstart_layer_key", key)
                    loaded_by_key[key] = qgs_layer
                added += 1
            else:
                failed += 1

        safety = len(pending_virtual) + 1
        while pending_virtual and safety > 0:
            safety -= 1
            remaining: List[Dict] = []
            progressed = False

            for vlayer in pending_virtual:
                qgs_layer = self._create_virtual_layer(vlayer, loaded_by_key)
                if qgs_layer and qgs_layer.isValid():
                    self._apply_qml_style(qgs_layer, vlayer)
                    self._add_layer_to_named_group(project, qgs_layer, vlayer)
                    key = self.layer_key(vlayer)
                    if key:
                        qgs_layer.setCustomProperty("projektstart_layer_key", key)
                        loaded_by_key[key] = qgs_layer
                    added += 1
                    progressed = True
                else:
                    remaining.append(vlayer)

            if not progressed:
                failed += len(remaining)
                break
            pending_virtual = remaining

        return added, failed

    def _add_layer_to_named_group(self, project: QgsProject, qgs_layer, layer: Dict) -> None:
        group_name = str(layer.get("project_group") or layer.get("__group_name") or "Import")
        root = project.layerTreeRoot()
        group = root.findGroup(group_name)
        if group is None:
            group = root.addGroup(group_name)
        project.addMapLayer(qgs_layer, addToLegend=False)
        group.addLayer(qgs_layer)

    def _create_non_virtual_layer(self, layer: Dict):
        source = self._resolve_layer_source(layer)
        source_type = str(layer.get("source_type", "")).lower()
        name = layer.get("name", "Layer")

        if source_type in {"wms", "xyz", "tiles"}:
            return QgsRasterLayer(source, name, "wms")
        if source_type == "mbtiles":
            return QgsRasterLayer(source, name, "gdal")
        if source_type == "wfs":
            return QgsVectorLayer(source, name, "WFS")
        if source_type in {"postgres", "postgis", "postgresql"}:
            uri = self._build_postgres_uri(layer)
            return QgsVectorLayer(uri, name, "postgres")
        if source_type in {"sqlite", "spatialite"}:
            return self._create_sqlite_layer(layer)

        candidate = QgsVectorLayer(source, name, "ogr")
        if candidate.isValid():
            return candidate
        return QgsRasterLayer(source, name)

    def _create_sqlite_layer(self, layer: Dict):
        name = layer.get("name", "Layer")
        source = self._resolve_layer_source(layer)
        table = str(layer.get("table", "")).strip()
        geometry_column = str(layer.get("geometry_column", "")).strip()
        key_column = str(layer.get("key_column", "")).strip()
        sql_filter = str(layer.get("where", "")).strip()
        explicit_uri = str(layer.get("uri", "")).strip()

        spatialite_uri = explicit_uri or self._build_sqlite_uri(source, table, geometry_column, key_column, sql_filter)

        if table and not geometry_column:
            ogr_source = f"{source}|layername={table}" if source else ""
            if ogr_source:
                ogr_layer = QgsVectorLayer(ogr_source, name, "ogr")
                if ogr_layer.isValid():
                    return ogr_layer

        if spatialite_uri:
            sqlite_layer = QgsVectorLayer(spatialite_uri, name, "spatialite")
            if sqlite_layer.isValid():
                return sqlite_layer

        if table:
            ogr_source = f"{source}|layername={table}" if source else ""
            if ogr_source:
                ogr_layer = QgsVectorLayer(ogr_source, name, "ogr")
                if ogr_layer.isValid():
                    return ogr_layer

        if explicit_uri:
            ogr_layer = QgsVectorLayer(explicit_uri, name, "ogr")
            if ogr_layer.isValid():
                return ogr_layer

        if source:
            ogr_layer = QgsVectorLayer(source, name, "ogr")
            if ogr_layer.isValid():
                return ogr_layer

        return None

    def _build_sqlite_uri(
        self,
        source: str,
        table: str,
        geometry_column: str,
        key_column: str,
        sql_filter: str,
    ) -> str:
        if not source:
            return ""

        if table:
            parts = [f"dbname='{source}'", f'table="{table}"']
            if geometry_column:
                parts[-1] = f'{parts[-1]} ({geometry_column})'
            if sql_filter:
                parts.append(f"sql={sql_filter}")
            if key_column:
                parts.append(f"key='{key_column}'")
            return " ".join(parts)

        return f"dbname='{source}'"

    def _build_postgres_uri(self, layer: Dict) -> str:
        host = str(layer.get("host", ""))
        port = str(layer.get("port", "5432"))
        dbname = str(layer.get("database", ""))
        schema = str(layer.get("schema", "public"))
        table = str(layer.get("table", ""))
        geometry_column = str(layer.get("geometry_column", "geom"))
        key_column = str(layer.get("key_column", "id"))
        sql_filter = str(layer.get("where", ""))
        auth_config_id = self._resolve_auth_config_id(layer)

        if layer.get("uri"):
            uri = QgsDataSourceUri(str(layer.get("uri")))
            if auth_config_id:
                uri.setAuthConfigId(auth_config_id)
            return uri.uri(False)

        uri = QgsDataSourceUri()
        uri.setConnection(host, port, dbname, "", "")
        if auth_config_id:
            uri.setAuthConfigId(auth_config_id)
        uri.setDataSource(schema, table, geometry_column, sql_filter, key_column)
        return uri.uri(False)

    def _resolve_auth_config_id(self, layer: Dict) -> str:
        explicit_authcfg = str(layer.get("authcfg", "")).strip()
        if explicit_authcfg:
            return explicit_authcfg

        auth_name = str(layer.get("authname", "")).strip()
        if not auth_name:
            return ""

        auth_name_lower = auth_name.casefold()

        auth_manager = QgsApplication.authManager()
        if not auth_manager:
            return ""

        for authcfg in auth_manager.configIds() or []:
            if str(authcfg).strip() == auth_name:
                return str(authcfg)

            config = QgsAuthMethodConfig()
            if auth_manager.loadAuthenticationConfig(authcfg, config, True):
                config_name = str(config.name() or "").strip()
                if config_name.casefold() == auth_name_lower:
                    return str(authcfg)
        return ""

    def _find_dependency_layer(self, dependency_key: str, loaded_by_key: Dict[str, object]):
        if dependency_key in loaded_by_key:
            return loaded_by_key[dependency_key]

        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if str(layer.customProperty("projektstart_layer_key", "")) == dependency_key:
                return layer
            if layer.name() == dependency_key:
                return layer
        return None

    def _create_virtual_layer(self, layer: Dict, loaded_by_key: Dict[str, object]):
        sql = str(layer.get("sql", "")).strip()
        if not sql:
            return None

        dependencies = layer.get("dependencies", []) or []
        dependency_aliases = layer.get("dependency_aliases", {}) or {}

        definition = QgsVirtualLayerDefinition()
        definition.setQuery(sql)

        for dependency_key in dependencies:
            dep_layer = self._find_dependency_layer(str(dependency_key), loaded_by_key)
            if not dep_layer:
                return None
            alias = str(dependency_aliases.get(str(dependency_key), str(dependency_key)))
            definition.addSource(alias, dep_layer.id())

        return QgsVectorLayer(definition.toString(), layer.get("name", "Virtueller Layer"), "virtual")

    def _apply_qml_style(self, qgs_layer, layer: Dict) -> None:
        qml_path = self._resolve_selected_qml_path(layer)
        if qml_path and qml_path.exists():
            qgs_layer.loadNamedStyle(str(qml_path))
            qgs_layer.triggerRepaint()

    def collect_qml_style_options(self, layer: Dict) -> List[Dict[str, str]]:
        options: List[Dict[str, str]] = []
        raw_styles = layer.get("qml_styles", []) or []
        for idx, raw in enumerate(raw_styles):
            if isinstance(raw, str) and raw.strip():
                options.append({"label": Path(raw.strip()).stem or f"Style {idx + 1}", "qml": raw.strip()})
                continue

            if not isinstance(raw, dict):
                continue
            qml_path = str(raw.get("qml") or raw.get("style_qml") or "").strip()
            if not qml_path:
                continue
            label = str(raw.get("label") or raw.get("name") or Path(qml_path).stem or f"Style {idx + 1}")
            options.append({"label": label, "qml": qml_path})
        return options

    def _resolve_selected_qml_path(self, layer: Dict) -> Optional[Path]:
        selected_qml = str(layer.get("__selected_qml", "__standard__")).strip()
        if selected_qml and selected_qml != "__standard__":
            return self._resolve_catalog_relative_path_for_item(selected_qml, layer)
        return self._resolve_qml_path(layer)

    def _resolve_qml_path(self, layer: Dict) -> Optional[Path]:
        explicit_qml = layer.get("qml") or layer.get("style_qml")
        if explicit_qml:
            return self._resolve_catalog_relative_path_for_item(str(explicit_qml), layer)

        source = self._resolve_layer_source(layer)
        if not source or "://" in source:
            return None

        source_path = Path(source)
        if source_path.suffix:
            return source_path.with_suffix(".qml")
        return Path(f"{source}.qml")

    def _resolve_catalog_relative_path(self, raw_path: str) -> Optional[Path]:
        path_value = str(raw_path).strip()
        if not path_value:
            return None
        if self._is_absolute_catalog_path(path_value):
            return Path(path_value)
        server_path = self._server_catalog_path()
        server_root = server_path.parent if server_path else None
        if server_root:
            return Path(self._join_catalog_path(str(server_root), path_value))
        return Path(self._join_catalog_path(str(self.plugin_dir), path_value))

    def _resolve_catalog_relative_path_for_item(self, raw_path: str, item: Dict) -> Optional[Path]:
        path_value = str(raw_path).strip()
        if not path_value:
            return None

        if self._is_absolute_catalog_path(path_value):
            return Path(path_value)

        catalog_root = str(item.get("__catalog_root", "")).strip()
        if catalog_root:
            return Path(self._join_catalog_path(catalog_root, path_value))
        return self._resolve_catalog_relative_path(path_value)

    def _resolve_layer_source(self, layer: Dict) -> str:
        raw_source = str(layer.get("source", "")).strip()
        if not raw_source:
            return ""
        if "://" in raw_source:
            return raw_source
        resolved = self._resolve_catalog_relative_path_for_item(raw_source, layer)
        return str(resolved) if resolved else raw_source

    def _publish_user_variables(self) -> None:
        project = QgsProject.instance()
        variables = {
            "user_firstname": self.settings.get("firstname", ""),
            "user_lastname": self.settings.get("lastname", ""),
            "user_phone": self.settings.get("phone", ""),
            "user_mail": self.settings.get("mail", ""),
            "user_department": self.settings.get("department", ""),
        }
        custom = project.customVariables()
        custom.update(variables)
        project.setCustomVariables(custom)

    def check_for_updates(self) -> None:
        server_path = self._server_catalog_path()
        if not server_path or not server_path.exists():
            QMessageBox.warning(self.iface.mainWindow(), tr("Updateprüfung"), tr("Katalogdatei am Server nicht gefunden."))
            return

        server_catalog = self._normalize_catalog(self._read_json(server_path))
        local_catalog = self._normalize_catalog(self._read_json(self.local_catalog_path))

        server_version = str(server_catalog.get("version", "0"))
        local_version = str(local_catalog.get("version", "0"))
        outdated = self._collect_outdated_layer_keys(local_catalog, server_catalog)
        self.outdated_layer_keys = outdated

        if server_version > local_version or outdated:
            QMessageBox.information(
                self.iface.mainWindow(),
                tr("Update verfügbar"),
                tr(
                    f"Serverversion {server_version} ist neuer als lokal {local_version}. "
                    f"Layer mit neueren Serverständen: {len(outdated)}."
                ),
            )
        else:
            QMessageBox.information(self.iface.mainWindow(), tr("Updateprüfung"), tr("Keine neuere Version gefunden."))

    def _source_to_path(self, source: str) -> Optional[Path]:
        if not source or "://" in source:
            return None
        return Path(source)

    def export_offline_package(self) -> None:
        cache_dir = self.settings.get("cache_dir", "") or self.default_cache_dir
        
        target = Path(self._resolve_cache_dir(cache_dir))
        target.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        for category in self.catalog.get("layer_categories", []):
            for subgroup in category.get("groups", []):
                for layer in subgroup.get("layers", []):
                    if layer.get("allow_offline_copy") is False:
                        skipped += 1
                        continue
                    if layer.get("source_type") in {"wms", "wfs", "xyz"}:
                        skipped += 1
                        continue
                    source = self._source_to_path(str(layer.get("source", "")))
                    if not source or not source.exists():
                        skipped += 1
                        continue
                    dest = target / source.name
                    if source.is_dir():
                        shutil.copytree(source, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, dest)
                    copied += 1

        QMessageBox.information(
            self.iface.mainWindow(),
            tr("Offline-Paket"),
            tr(f"Offline-Daten bereitgestellt. Kopiert: {copied}, übersprungen: {skipped}."),
        )
