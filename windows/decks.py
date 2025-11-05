from functools import partial
import sqlite3
import time
import json
from collections import defaultdict

from windows.study import StudyWindow
from windows.browse import BrowseWindow
from media import copy_media_file


from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSpacerItem,
    QSizePolicy, QTreeWidget, QTreeWidgetItem, QPushButton, QDialog,
    QHeaderView, QToolButton, QMenu, QInputDialog, QMessageBox,
    QFormLayout, QLineEdit, QLabel, QComboBox, QScrollArea, QTextEdit,
    QGroupBox, QSplitter, QFileDialog
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QBrush, QColor, QAction, QCursor, QIcon
QT_BACKEND = "PySide6"


class DeckWidget(QTreeWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        header = self.header()
        header.setSectionResizeMode(QHeaderView.Interactive)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_proportions()

    def _apply_proportions(self):
        header = self.header()
        total_w = max(0, self.viewport().width())
        deck_col = int(total_w * 0.60)

        remaining = max(0, total_w - deck_col)
        if remaining <= 0:
            w1 = w2 = w3 = 30
        else:
            w1 = max(30, remaining // 3)
            w2 = max(30, remaining // 3)
            w3 = max(30, remaining - (w1 + w2))

        header.resizeSection(0, deck_col)
        header.resizeSection(1, w1)
        header.resizeSection(2, w2)
        header.resizeSection(3, w3)

class DecksWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kioku")
        self.resize(708, 592) # (width, height)
        self.setWindowIcon(QIcon('icon\\lightbulb.ico'))

        # Central container of app
        central = QWidget()
        central.setObjectName("central")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central.setStyleSheet("""
            QWidget#central { background: #2c2c2c; }
        """)
        self.setCentralWidget(central)

        self.db_conn = self._open_db()

        # Nav bar
        nav_container = QWidget()
        nav_container.setObjectName("nav_container")
        nav_container.setFixedWidth(350)
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(nav_container, alignment=Qt.AlignHCenter)
        central_layout.addItem(QSpacerItem(20, -2, QSizePolicy.Minimum, QSizePolicy.Fixed))

        btn_names = ["Decks", "Add", "Browse", "Stats", "Import"]
        for name in btn_names:
            btn = QPushButton(name)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            font = btn.font()
            font.setPointSize(11)
            font.setBold(True)
            btn.setFont(font)
            
            if name == "Add":
                add_menu = QMenu(btn)
                
                deck_action = QAction("Deck", btn)
                card_type_action = QAction("Card Type", btn)
                card_action = QAction("Card", btn)
                
                deck_action.triggered.connect(partial(self._on_new_deck_clicked))
                card_type_action.triggered.connect(partial(self.on_new_card_type_clicked))
                card_action.triggered.connect(partial(self.on_new_card_clicked))
                
                add_menu.addAction(deck_action)
                add_menu.addAction(card_type_action)
                add_menu.addAction(card_action)
                btn.setMenu(add_menu)
            elif name == "Browse":
                btn.clicked.connect(self.open_browse_window)
            elif name == "Stats":
                btn.clicked.connect(partial(self._show_warning, "Stats", "Stats are not supported yet."))
            elif name == "Import":
                btn.clicked.connect(partial(self._show_warning, "Import", "Imports are not supported yet."))
            nav_layout.addWidget(btn)

        nav_container.setStyleSheet("""      
            QWidget#nav_container {
                background: #373737;
                border: 1px solid #1f1f1f;
                border-radius: 5px;
            }
            #nav_container QPushButton {
                color: white;
                background: transparent;
                border: none;
                padding: 6px 5px;
            }
            #nav_container QPushButton:hover {
                background: transparent;
                border: 1px solid #1f1f1f;
            } 
            #nav_container QPushButton:pressed {
                background: transparent;
            }
            #nav_container QPushButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)
        central_layout.addWidget(nav_container, alignment=Qt.AlignHCenter)
        central_layout.addItem(QSpacerItem(20, 8, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # Deck widget
        deck_widget_container = QHBoxLayout()
        central_layout.addLayout(deck_widget_container)
        deck_widget_container.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.deck_widget = DeckWidget()
        self.deck_widget.setObjectName("deck_widget")
        self.deck_widget.setFixedSize(550, 300)
        self.deck_widget.setAutoFillBackground(False)
        self.deck_widget.viewport().setAutoFillBackground(False)
        self.deck_widget.setColumnCount(4)
        self.deck_widget.setHeaderLabels(["Deck", "New", "Learn", "Due"])

        header = self.deck_widget.header()
        font = QFont()
        font.setPointSize(11)
        header.setFont(font)
        header.setStyleSheet("""
            QHeaderView {    
                background-color: #303030;
                border: none;
            }
            QHeaderView::section {
                background-color: #303030;
                color: white;
                padding: 6px 6px 0px 6px;
                border: none;
                border-bottom: 1px solid #1f1f1f;
                font-weight: bold;
            }
        """)

        font = QFont()
        font.setPointSize(11)
        self.deck_widget.setFont(font)
        self.deck_widget.setIndentation(16)
        self.deck_widget.setStyleSheet("""
        QTreeWidget#deck_widget {
            background: transparent;
            background-color: #303030;
            padding: 4px;
        }
        QTreeView::item {
            padding: 5px 0px;
        }
        """)

        self.settings_buttons = {}

        deck_widget_container.addWidget(self.deck_widget)
        deck_widget_container.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        central_layout.addItem(QSpacerItem(20, 24, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.deck_widget.currentItemChanged.connect(self._on_deck_item_selected)
        self.deck_widget.itemActivated.connect(self.open_study_window)

        # Study time
        self.total_time = float(0)
        self.num_studied = 0
        self.study_stats_label = QLabel()
        self.study_stats_label.setAlignment(Qt.AlignCenter)
        self.study_stats_label.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 14px;
                padding: 6px;
                background-color: #252525;
                border-top: 1px solid #1f1f1f;
            }
        """)
        central_layout.addWidget(self.study_stats_label)

        self.study_win = None
        self.browse_win = None

        # Initialisation
        self._ensure_srs_columns()
        cur = self.db_conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM decks")
        self._populate_deck_tree_from_db()

    def _show_warning(self, title, warning):
        QMessageBox.warning(self, title, warning)

    def _colour_number(self, item, val, col):
        txt = str(val) if val is not None and val != 0 else "0"
        item.setText(col, txt)
        if val == 0:
            color = "#9e9e9e"
        else:
            if col == 1:
                color = "#4ea0ff"
            elif col == 2:
                color = "#ff6b6b"
            elif col == 3:
                color = "#4cd97b"
            else:
                color = "#e6e6e6"
        item.setForeground(col, QBrush(QColor(color)))

    def _on_deck_options_clicked(self, deck):
        menu = QMenu(self)
        opt_action = QAction("Options", self)
        del_action = QAction("Delete", self)
        menu.addAction(opt_action)
        menu.addAction(del_action)

        def _find_item(deck_id):
            root = self.deck_widget.invisibleRootItem()
            stack = [root]
            while stack:
                parent = stack.pop()
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    if child.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                        return child
                    stack.append(child)
            return None
        
        item = _find_item(deck["id"])

        opt_action.triggered.connect(lambda: QMessageBox.warning(self, "Deck options", "Deck options are not supported yet."))
        del_action.triggered.connect(lambda: self._confirm_delete_deck(deck["id"], item))

        menu.exec_(QCursor.pos())

    def _confirm_delete_deck(self, deck_id, item):
        if deck_id is None:
            QMessageBox.warning(self, "Delete deck", "The 'Collection' deck cannot be deleted.")
            return

        deck_name = item.text(0) if item is not None else str(deck_id)
        reply = QMessageBox.question(
            self,
            "Delete deck",
            f"Are you sure you want to delete the deck '{deck_name}', including its subdecks and cards?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self._delete_deck_and_subtree(deck_id)
            QMessageBox.information(self, "Deck deleted", f"Deck '{deck_name}' and its subdecks and cards have been deleted.")
            self._populate_deck_tree_from_db()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete deck: {e}")

    def _delete_deck_and_subtree(self, deck_id):
        cur = self.db_conn.cursor()

        # Get subtree ids using a recursive CTE
        cur.execute("""
            WITH RECURSIVE subdecks(id) AS (
                SELECT id FROM decks WHERE id = ?
                UNION ALL
                SELECT d.id FROM decks d JOIN subdecks s ON d.parent_deck_id = s.id
            )
            SELECT id FROM subdecks;
        """, (deck_id,))
        rows = cur.fetchall()
        subtree_ids = [r["id"] for r in rows]
        if not subtree_ids:
            return

        placeholders = ",".join("?" for _ in subtree_ids)
        cur.execute(f"DELETE FROM cards WHERE deck_id IN ({placeholders})", tuple(subtree_ids))
        cur.execute(f"DELETE FROM decks WHERE id IN ({placeholders})", tuple(subtree_ids))

        self.db_conn.commit()

    def _open_db(self, path="database.db", schema_path="schema.sql"):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        with open(schema_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
            conn.executescript(sql_script)
        conn.commit()
        return conn

    def _ensure_srs_columns(self):
        cur = self.db_conn.cursor()
        cur.execute("PRAGMA table_info(cards)")
        cols = {row["name"] for row in cur.fetchall()}

        alters = []
        if "reps" not in cols:
            alters.append("ALTER TABLE cards ADD COLUMN reps INTEGER DEFAULT 0")
        if "interval" not in cols:
            alters.append("ALTER TABLE cards ADD COLUMN interval INTEGER DEFAULT 0")
        if "ease" not in cols:
            alters.append("ALTER TABLE cards ADD COLUMN ease REAL DEFAULT 2.5")
        if "last_reviewed" not in cols:
            alters.append("ALTER TABLE cards ADD COLUMN last_reviewed INTEGER")
        if "learning_step_index" not in cols:
            alters.append("ALTER TABLE cards ADD COLUMN learning_step_index INTEGER DEFAULT 0")

        for sql in alters:
            try:
                cur.execute(sql)
            except Exception as e:
                print("Warning running:", sql, ": ", e)

        self.db_conn.commit()

    def _load_decks_and_counts(self):
        cur = self.db_conn.cursor()
        cur.execute("SELECT id, name, parent_deck_id FROM decks")
        decks = [dict(row) for row in cur.fetchall()]

        now = int(time.time())
        cur.execute("""
            SELECT deck_id,
                SUM(CASE WHEN reps = 0 AND learning_step_index = 0 AND (next_due IS NULL) THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN reps = 0 AND (learning_step_index > 0 OR (next_due IS NOT NULL AND next_due > ?)) THEN 1 ELSE 0 END) AS learn_count,
                SUM(CASE WHEN next_due IS NOT NULL AND next_due <= ? THEN 1 ELSE 0 END) AS due_count
            FROM cards
            WHERE is_active = 1
            GROUP BY deck_id
        """, (now, now))
        raw = {row["deck_id"]: (row["new_count"] or 0, row["learn_count"] or 0, row["due_count"] or 0)
            for row in cur.fetchall()}
        
        deck_ids = {deck["id"] for deck in decks}
        for did in deck_ids:
            raw.setdefault(did, (0, 0, 0))

        children = defaultdict(list)
        root_ids = []
        for deck in decks:
            pid = deck["parent_deck_id"]
            if pid is None:
                root_ids.append(deck["id"])
            else:
                children[pid].append(deck["id"])

        totals = {}

        def dfs_aggregate(did):
            new, learn, due = raw.get(did, (0, 0, 0))
            for ch in children.get(did, ()):
                cn, cl, cd = dfs_aggregate(ch)
                new += cn
                learn += cl
                due += cd
            totals[did] = (new, learn, due)
            return totals[did]

        for rid in root_ids:
            dfs_aggregate(rid)
        for did in deck_ids - set(totals.keys()):
            dfs_aggregate(did)

        return decks, totals

    def _populate_deck_tree_from_db(self):
        self.deck_widget.clear()
        self.settings_buttons.clear()

        decks, totals = self._load_decks_and_counts()
        deck_map = {deck["id"]: deck for deck in decks}
        children = defaultdict(list)
        for deck in decks:
            parent_deck_id = deck["parent_deck_id"]
            children[parent_deck_id].append(deck["id"])
        item_map = {}

        def create_deck(deck_id, parent_item=None):
            deck = deck_map[deck_id]
            item = QTreeWidgetItem(parent_item or self.deck_widget, [deck["name"], "", "", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, deck_id)
            item.setExpanded(True)
            item_map[deck_id] = item
            
            new_card, learn_card, due_card = totals.get(deck_id, (0, 0, 0))
            self._colour_number(item, new_card, 1)
            self._colour_number(item, learn_card, 2)
            self._colour_number(item, due_card, 3)

            settings_btn = QToolButton()
            settings_btn.setText("⚙")
            settings_btn.setCursor(Qt.PointingHandCursor)
            settings_btn.setStyleSheet("QToolButton { background: transparent; color: #cccccc; border: none; font-size: 16px; }")
            settings_btn.clicked.connect(partial(self._on_deck_options_clicked, deck))
            settings_btn.setVisible(False)
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.addStretch()
            container_layout.addWidget(settings_btn)
            self.deck_widget.setItemWidget(item, 3, container)
            
            self.settings_buttons[item] = settings_btn

            for child_id in children.get(deck_id, ()):
                create_deck(child_id, item)

            return item

        top_ids = [deck["id"] for deck in decks if deck["parent_deck_id"] is None]
        for top_id in top_ids:
            create_deck(top_id)

        orphans = [deck["id"] for deck in decks if deck["parent_deck_id"] is not None and deck["parent_deck_id"] not in deck_map]
        for orphan_id in orphans:
            create_deck(orphan_id)

        # Add blank row as margin between decks and header
        blank_row = QTreeWidgetItem()
        blank_row.setText(0, "")
        blank_row.setDisabled(True)
        blank_row.setFlags(blank_row.flags() & ~Qt.ItemIsSelectable)
        blank_row.setSizeHint(0, QSize(0, 10))
        self.deck_widget.insertTopLevelItem(0, blank_row)

    def _create_deck(self, name: str, parent_deck_id: int | None = None) -> int:
        cur = self.db_conn.cursor()
        cur.execute("INSERT INTO decks (name, parent_deck_id) VALUES (?, ?)", (name, parent_deck_id))
        self.db_conn.commit()
        return cur.lastrowid

    def _on_new_deck_clicked(self):
        name, ok = QInputDialog.getText(self, "Create deck", "Deck name:")
        if not ok or not name.strip():
            return

        parts = [part.strip() for part in name.split("->") if part.strip()]
        if not parts:
            return

        parent_deck_id = None
        for part in parts:
            cur = self.db_conn.cursor()
            cur.execute(
                "SELECT id FROM decks WHERE name = ? AND (parent_deck_id IS ? OR parent_deck_id = ?)",
                (part, parent_deck_id, parent_deck_id),
            )
            row = cur.fetchone()
            if row:
                parent_deck_id = row[0]
            else:
                parent_deck_id = self._create_deck(part, parent_deck_id)

        self._populate_deck_tree_from_db()

    def create_card_type(self, name: str, field_names: list, template_front: str = "", template_back: str = "") -> int:
        fields = json.dumps(field_names, ensure_ascii=False)
        modified = int(time.time())
        cur = self.db_conn.cursor()
        cur.execute(
            "INSERT INTO card_types (fields, name, template_front, template_back, modified_at) VALUES (?, ?, ?, ?, ?)",
            (fields, name, template_front, template_back, modified)
        )
        self.db_conn.commit()
        return cur.lastrowid

    def create_card(self, card_type_id: int, deck_id: int, field_values: dict, template_front: str = "", template_back: str = "", tags: str = "") -> int:
        fields = json.dumps(field_values, ensure_ascii=False)
        created = int(time.time())
        cur = self.db_conn.cursor()
        cur.execute(
            """INSERT INTO cards (card_type_id, deck_id, fields, is_active, created_at, next_due, template_front, template_back, tags)
            VALUES (?, ?, ?, 1, ?, NULL, ?, ?, ?)""",
            (card_type_id, deck_id, fields, created, template_front, template_back, tags)
        )
        self.db_conn.commit()
        return cur.lastrowid

    def on_new_card_type_clicked(self):
        dialog = NewCardTypeDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, fields, template_front, template_back = dialog.get_data()
        if not fields:
            QMessageBox.warning(self, "Validation error", "You must provide at least one field name.")
            return

        new_id = self.create_card_type(name, fields, template_front, template_back)
        QMessageBox.information(self, "Card type created", f"Card type created (id={new_id}).")

    def get_card_types(self):
        cur = self.db_conn.cursor()
        cur.execute("SELECT id, name, fields, template_front, template_back, modified_at FROM card_types")
        rows = []
        for row in cur.fetchall():
            fields = json.loads(row["fields"]) if row["fields"] else []
            rows.append({
                "id": row["id"],
                "name": row["name"],
                "fields": fields,
                "template_front": row["template_front"],
                "template_back": row["template_back"],
                "modified_at": row["modified_at"]
            })
        return rows

    def get_decks(self):
        cur = self.db_conn.cursor()
        cur.execute("SELECT id, name, parent_deck_id FROM decks")
        return [dict(row) for row in cur.fetchall()]

    def on_new_card_clicked(self):
        card_types = self.get_card_types()
        if not card_types:
            QMessageBox.warning(self, "No card types", "You must create a card type before creating cards.")
            return
        decks = self.get_decks()
        if not decks:
            QMessageBox.warning(self, "No decks", "You must create a deck before creating cards.")
            return

        dialog = NewCardDialog(card_types, decks, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        card_type_id, deck_id, field_values, template_front, template_back, tags = dialog.get_data()
        if not all(val.strip() for val in field_values.values()):
            proceed = QMessageBox.question(
                self, "Empty fields", "One or more fields are empty. Create card anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if proceed != QMessageBox.Yes:
                return

        new_id = self.create_card(card_type_id, deck_id, field_values, template_front, template_back, tags)

        self._populate_deck_tree_from_db()

    def _on_deck_item_selected(self, current):
        for btn in self.settings_buttons.values():
            btn.setVisible(False)
        if current in self.settings_buttons:
            self.settings_buttons[current].setVisible(True)

    def open_study_window(self, item):
        if self.study_win is None:
            deck_id = item.data(0, Qt.ItemDataRole.UserRole)
            if deck_id is None:
                QMessageBox.information(self, "No deck id", "This item has no deck id.")
                return
            deck_id = item.data(0, Qt.ItemDataRole.UserRole)
            if deck_id is None:
                QMessageBox.information(self, "No deck id", "This item has no deck id.")
                return
            self.study_win = StudyWindow(self.db_conn, deck_id)
            self.study_win.show()
            self.study_win.closed.connect(lambda: self._on_study_win_closed(self.study_win.num_studied, self.study_win.total_time))
            self.study_win.destroyed.connect(lambda: setattr(self, "study_win", None))
        else:
            if self.study_win.isVisible():
                self.study_win.raise_()
                self.study_win.activateWindow()
            else:
                self.study_win = None
                self.open_study_window(item)
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)

    def _on_study_win_closed(self, num_studied, total_time):
        self.num_studied += num_studied
        self.total_time += total_time
        hrs = int(self.total_time // 3600)
        mins = int((self.total_time % 3600) // 60)
        hrs_str = ""
        mins_str = ""
        if hrs == 1:
            hrs_str = "hr"
        else:
            hrs_str = "hrs"
        if mins == 1:
            mins_str = "min"
        else:
            mins_str = "mins"
        if num_studied != 0:
            self.study_stats_label.setText(f"# Cards: {self.num_studied} | Time: {hrs} {hrs_str} {mins} {mins_str} ({(total_time/num_studied):.2f}s/card)")
        self._populate_deck_tree_from_db()

    def open_browse_window(self):
        if self.browse_win is None:
            self.browse_win = BrowseWindow(self.db_conn)
            self.browse_win.show()
            self.browse_win.destroyed.connect(lambda: setattr(self, "browse_win", None))
        else:
            if self.browse_win.isVisible():
                self.browse_win.raise_()
                self.browse_win.activateWindow()
            else:
                self.browse_win = None
                self.open_browse_window()

class NewCardTypeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Card Type")
        self.resize(480, 200)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_in = QLineEdit()
        self.fields_in = QLineEdit()
        self.template_front_in = QLineEdit()
        self.template_back_in = QLineEdit()

        form.addRow("Name:", self.name_in)
        form.addRow("Fields:", self.fields_in)
        form.addRow("Front Template: ", self.template_front_in)
        form.addRow("Back Template: ", self.template_back_in)

        layout.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("Create")
        cancel = QPushButton("Cancel")
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def get_data(self):
        name = self.name_in.text().strip()
        raw_fields = self.fields_in.text().strip()
        template_front = self.template_front_in.text().strip()
        template_back = self.template_back_in.text().strip()
        fields = [field.strip() for field in raw_fields.split(",") if field.strip()]
        return name, fields, template_front, template_back

class NewCardDialog(QDialog):
    def __init__(self, card_types, decks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Card")
        self.resize(900, 640)

        self.card_types = card_types or []
        self.decks = decks or []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)

        picks_row = QHBoxLayout()
        picks_row.setSpacing(14)
        picks_row.addWidget(QLabel("Card type:"))
        self.card_type_combo = QComboBox()
        for card_type in self.card_types:
            self.card_type_combo.addItem(card_type.get("name", f"Type {card_type['id']}"), card_type["id"])
        self.card_type_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        picks_row.addWidget(self.card_type_combo)

        picks_row.addSpacing(16)
        picks_row.addWidget(QLabel("Deck:"))
        self.deck_combo = QComboBox()
        for deck in self.decks:
            self.deck_combo.addItem(deck["name"], deck["id"])
        self.deck_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        picks_row.addWidget(self.deck_combo)

        picks_row.addWidget(QLabel("Tags (optional):"))
        self.tags_in = QLineEdit()
        picks_row.addWidget(self.tags_in)

        picks_row.addStretch()
        outer.addLayout(picks_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        left_box = QGroupBox()
        left_box_layout = QVBoxLayout(left_box)
        left_box_layout.setContentsMargins(8, 8, 8, 8)
        left_box_layout.setSpacing(6)

        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_container = QWidget()
        self.fields_layout = QFormLayout(self.fields_container)
        self.fields_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.fields_layout.setFormAlignment(Qt.AlignTop)
        self.fields_scroll.setWidget(self.fields_container)
        left_box_layout.addWidget(self.fields_scroll)

        splitter.addWidget(left_box)

        right_box = QGroupBox()
        right_box_layout = QVBoxLayout(right_box)
        right_box_layout.setContentsMargins(8, 8, 8, 8)
        right_box_layout.setSpacing(8)

        front_label = QLabel("Front template")
        front_label.setFont(header_font)
        right_box_layout.addWidget(front_label)

        self.front_edit = QTextEdit()
        self.front_edit.setAcceptRichText(False)
        self.front_edit.setPlaceholderText("Enter front template")
        self.front_edit.setMinimumHeight(180)
        right_box_layout.addWidget(self.front_edit, stretch=1)

        back_label = QLabel("Back template")
        back_label.setFont(header_font)
        right_box_layout.addWidget(back_label)

        self.back_edit = QTextEdit()
        self.back_edit.setAcceptRichText(False)
        self.back_edit.setPlaceholderText("Enter back template")
        self.back_edit.setMinimumHeight(180)
        right_box_layout.addWidget(self.back_edit, stretch=1)

        splitter.addWidget(right_box)

        splitter.setStretchFactor(0, 80)
        splitter.setStretchFactor(1, 20)
        outer.addWidget(splitter, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Create")
        cancel = QPushButton("Cancel")
        ok.setDefault(True)
        ok.setFixedWidth(120)
        cancel.setFixedWidth(120)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        outer.addLayout(btn_row)

        self.setStyleSheet("""
            QGroupBox { 
                border: 1px solid #3a3a3a; 
                border-radius: 8px; 
                margin-top: 6px;
                background: #262626;
                color: #eaeaea;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLabel { color: #dddddd; }
            QLineEdit, QTextEdit, QComboBox { 
                background: #1f1f1f; 
                color: #f0f0f0; 
                border: 1px solid #2b2b2b; 
                padding: 6px;
            }
            QPushButton { 
                background: #2d2d2d; 
                color: #ffffff; 
                border: 1px solid #3a3a3a; 
                padding: 6px 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #3b3b3b; }
        """)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.card_type_combo.currentIndexChanged.connect(self.rebuild_fields)

        if self.card_types:
            self.card_type_combo.setCurrentIndex(0)
            self.rebuild_fields()
        else:
            self.front_edit.setPlainText("")
            self.back_edit.setPlainText("")

    def attach_file(self, field):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select media file",
            "",
            "Media files (*.png *.jpg *.jpeg *.gif *.bmp *.mp3 *.wav *.ogg *.m4a)"
        )
        if not path:
            return
        try:
            filename = copy_media_file(path)
        except Exception as e:
            QMessageBox.warning(self, "Attach failed", f"Failed to copy file: {e}")
            return
        field.setText(filename)

    def rebuild_fields(self, index=None):
        while self.fields_layout.rowCount():
            self.fields_layout.removeRow(0)

        idx = self.card_type_combo.currentIndex() if index is None else index
        if idx < 0:
            return
        card_type_id = self.card_type_combo.itemData(idx)
        card_type = next((card_type for card_type in self.card_types if card_type["id"] == card_type_id), None)
        if card_type is None:
            return

        self.field_widgets = {}
        for fname in card_type.get("fields", []):
            le = QLineEdit()
            attach_btn = QPushButton("Attach Image")

            h = QHBoxLayout()
            h.addWidget(le)
            h.addWidget(attach_btn)
            self.fields_layout.addRow(f"{fname}:", h)
            self.field_widgets[fname] = le
            attach_btn.clicked.connect(lambda _, field=le: self.attach_file(field))

        self.front_edit.setPlainText(card_type.get("template_front", "") or "")
        self.back_edit.setPlainText(card_type.get("template_back", "") or "")

    def get_data(self):
        card_type_idx = self.card_type_combo.currentIndex()
        card_type_id = self.card_type_combo.itemData(card_type_idx)

        deck_idx = self.deck_combo.currentIndex()
        deck_id = self.deck_combo.itemData(deck_idx) if deck_idx >= 0 else None

        field_values = {name: widget.text() for name, widget in getattr(self, "field_widgets", {}).items()}
        template_front = self.front_edit.toPlainText()
        template_back = self.back_edit.toPlainText()
        tags = self.tags_in.text()
        return card_type_id, deck_id, field_values, template_front, template_back, tags

    def validate(self):
        if self.card_type_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Validation error", "You must select a card type.")
            return False
        if self.deck_combo.currentIndex() < 0:
            QMessageBox.warning(self, "Validation error", "You must select a deck.")
            return False
        if not getattr(self, "field_widgets", {}):
            QMessageBox.warning(self, "Validation error", "The selected card type has no fields defined.")
            return False
        return True
