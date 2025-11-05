import time
import json
import os

from __init__ import LEARNING_STEPS, DAY, PLACEHOLDER_RE, convert_human_time
from media import ALLOWED_FORMATS, media_dir

try:
    from PySide6.QtWidgets import (
        QHBoxLayout, QVBoxLayout, QPushButton, QDialog, QMessageBox, 
        QTextBrowser, QFrame, QSizePolicy
    )
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import QIcon
    QT_BACKEND = "PySide6"
except Exception:
    from PyQt5.QtWidgets import (
        QHBoxLayout, QVBoxLayout, QPushButton, QDialog, QMessageBox,
        QTextBrowser, QFrame, QSizePolicy
    )
    from PyQt5.QtCore import Qt, QTimer, Signal
    from PyQt5.QtGui import QIcon
    QT_BACKEND = "PyQt5"

class StudyWindow(QDialog):
    closed = Signal()

    def __init__(self, db_conn, deck_id, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Study Deck")
        self.setStyleSheet("background-color: #373737;")
        self.resize(700, 560)
        self.setWindowIcon(QIcon('icon\\lightbulb.ico'))
        self.db_conn = db_conn
        self.deck_id = deck_id

        self.num_studied = 0
        self.start_time = None
        self.end_time = None
        self.total_time = float(0)

        self.cards = self._load_cards_for_deck(self.deck_id)
        self.index = 0

        if not self.cards:
            QMessageBox.information(self, "No cards", "This deck has no cards to study.")
            QTimer.singleShot(0, self.close)
            return

        layout = QVBoxLayout(self)

        self.front_view = QTextBrowser()
        self.front_view.setReadOnly(True)
        self.front_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.front_view, stretch=3)

        front_font = self.front_view.font()
        front_font.setPointSize(16)
        front_font.setBold(True)
        self.front_view.setFont(front_font)

        self.frame = QFrame()
        self.frame.setFrameShape(QFrame.HLine)
        self.frame.setVisible(False)
        layout.addWidget(self.frame)

        self.back_view = QTextBrowser()
        self.back_view.setReadOnly(True)
        self.back_view.setVisible(False)
        layout.addWidget(self.back_view, stretch=2)

        back_font = self.back_view.font()
        back_font.setPointSize(16)
        back_font.setBold(True)
        self.back_view.setFont(back_font)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_again = QPushButton("Again")
        self.btn_hard = QPushButton("Hard")
        self.btn_good = QPushButton("Good")
        self.btn_easy = QPushButton("Easy")
        for btn in (self.btn_again, self.btn_hard, self.btn_good, self.btn_easy):
            btn.setVisible(False)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.btn_again.clicked.connect(lambda: self._chosen(0))
        self.btn_hard.clicked.connect(lambda: self._chosen(3))
        self.btn_good.clicked.connect(lambda: self._chosen(4))
        self.btn_easy.clicked.connect(lambda: self._chosen(5))

        self.flipped = False
        self._show_current_card_front()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def _show_current_card_front(self):
        self.flipped = False
        card = self.cards[self.index]
        text = self._render_template(card["template_front"], card["fields"])
        self.front_view.setHtml(f"""{text}""")
        self.back_view.setVisible(False)
        self.frame.setVisible(False)
        
        self.btn_again.setVisible(False)
        self.btn_hard.setVisible(False)
        self.btn_good.setVisible(False)
        self.btn_easy.setVisible(False)
        
        self.start_time = time.time()

    def _show_current_card_back(self):
        card = self.cards[self.index]
        text = self._render_template(card["template_back"], card["fields"])
        self.back_view.setHtml(f"""{text}""")
        self.back_view.setVisible(True)
        self.frame.setVisible(True)
        self.flipped = True
        
        self.btn_again.setVisible(True)
        self.btn_hard.setVisible(True)
        self.btn_good.setVisible(True)
        self.btn_easy.setVisible(True)

        self.num_studied += 1
        self.end_time = time.time()
        self.total_time += (self.end_time - self.start_time)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Return:
            if not self.flipped:
                self._show_current_card_back()
            return
        if key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4):
            if not self.flipped:
                return
            mapping = {Qt.Key_1: 0, Qt.Key_2: 3, Qt.Key_3: 4, Qt.Key_4: 5}
            self._chosen(mapping[key])
            return
        super().keyPressEvent(event)

    def _chosen(self, quality=0):
        card = self.cards[self.index]
        cur = self.db_conn.cursor()
        cur.execute("SELECT id, reps, interval, ease, learning_step_index, next_due FROM cards WHERE id = ?", (card["id"],))
        row = cur.fetchone()
        if not row:
            print(f"Error: card {card['id']} not found in database.")
            return

        next_due, new_interval, new_reps, new_ease, new_lidx = self._compute_next_sm2(dict(row), quality)
        self._apply_review_to_card_sm2(card["id"], next_due, new_interval, new_reps, new_ease, new_lidx)

        self.index += 1
        if self.index >= len(self.cards):
            QMessageBox.information(self, "Done", "You have reached the end of the deck.")
            self.close()
            return
        self._show_current_card_front()

    # Ensure cards table has columns needed for SM-2 
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
                print("Error while running:", sql, ": ", e)
        self.db_conn.commit()

    def _get_subdeck_ids(self, deck_id):
        cur = self.db_conn.cursor()
        cur.execute("SELECT id FROM decks WHERE parent_deck_id = ?", (deck_id,))
        subdeck_rows = cur.fetchall()
        subdeck_ids = [row[0] for row in subdeck_rows]

        for sub_id in subdeck_ids[:]:
            subdeck_ids.extend(self._get_subdeck_ids(sub_id))
        
        return subdeck_ids

    def _load_cards_for_deck(self, deck_id):
        now = int(time.time())
        deck_ids = [deck_id] + self._get_subdeck_ids(deck_id)

        placeholders = ",".join("?" for did in deck_ids)
        query = f"""
            SELECT *
            FROM cards
            WHERE deck_id IN ({placeholders})
            AND is_active = 1
            AND (
                    (reps = 0 AND learning_step_index = 0 AND next_due IS NULL)      -- new
                OR (reps = 0 AND (learning_step_index > 0 OR (next_due IS NOT NULL AND next_due > ?))) -- learn             -- learning card now due
                OR (reps > 0 AND next_due <= ?)                                      -- review
            )
            ORDER BY
                CASE WHEN reps = 0 THEN 0 ELSE 1 END, next_due ASC, id ASC
        """

        cur = self.db_conn.cursor()
        cur.execute(query, (*deck_ids, now, now))
        rows = cur.fetchall()
        
        cards = []
        for row in rows:
            fields = {}
            try:
                fields = json.loads(row["fields"]) if row["fields"] else {}
            except Exception:
                fields = {}
            cards.append({
                "id": row["id"],
                "card_type_id": row["card_type_id"],
                "fields": fields,
                "card_ord": row["card_ord"],
                "next_due": row["next_due"],
                "template_front": row["template_front"] or "",
                "template_back": row["template_back"] or ""
            })
        return cards

    def _media_abs_path(self, filename):
        return os.path.join(media_dir(), filename)

    def _render_template(self, template: str, fields: dict) -> str:
        def replacer(match):
            key = match.group(1)
            val = fields.get(key, "")
            if not isinstance(val, str):
                return str(val)

            abs_path = self._media_abs_path(val)
            if os.path.isfile(abs_path):
                _, ext = os.path.splitext(val.lower())
                if ext in ALLOWED_FORMATS:
                    return f'<img src="file:///{abs_path}" style="width: 100px; height:auto; display:block; margin:6px 0;">'
            return str(val)

        html = PLACEHOLDER_RE.sub(replacer, template or "")
        return html

    def _mark_card_reviewed(self, card_id):
        next_due = int(time.time()) + 10 * 60
        cur = self.db_conn.cursor()
        cur.execute("UPDATE cards SET next_due = ? WHERE id = ?", (next_due, card_id))
        self.db_conn.commit()

    def _mark_card_reviewed(self, card_id):
        next_due = int(time.time()) + 10 * 60
        cur = self.db_conn.cursor()
        cur.execute("UPDATE cards SET next_due = ? WHERE id = ?", (next_due, card_id))
        self.db_conn.commit()

    def _advance_to_next_card(self):
        self.index += 1
        if self.index >= len(self.cards):
            QMessageBox.information(self, "Done", "You have reached the end of the deck.")
            self.close()
            return
        self._show_current_card_front()

    def _compute_next_sm2(self, card_row, quality: int):
        now = int(time.time())
        reps = int(card_row.get("reps", 0) or 0)
        interval = int(card_row.get("interval", 0) or 0)
        ease = float(card_row.get("ease", 2.5) or 2.5)
        lidx = int(card_row.get("learning_step_index", 0) or 0)

        if quality < 3: # Failed review, reset reps
            if reps == 0: # Advance learning step if possible
                next_lidx = min(lidx + 1, len(LEARNING_STEPS) - 1)
                next_due = now + LEARNING_STEPS[next_lidx]
                new_reps = 0
                new_interval = 0
                new_ease = ease
                new_lidx = next_lidx
            else: # If graduated card failed, use an immediate short interval (first learning step) and reset reps
                new_reps = 0
                new_interval = 0
                new_lidx = 0
                next_due = now + LEARNING_STEPS[0] if LEARNING_STEPS else now + 60
                new_ease = ease
        else: # Successful review
            if reps == 0: # If first successful review, graduate from learning
                new_reps = 1
                new_interval = DAY
                next_due = now + new_interval
                new_lidx = 0
                q = quality
                new_ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
                if new_ease < 1.3:
                    new_ease = 1.3
            else: # If already learned, apply SM-2
                q = quality
                new_ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
                if new_ease < 1.3:
                    new_ease = 1.3

                new_reps = reps + 1
                if reps == 1:
                    new_interval = 6 * DAY
                else:
                    if interval <= 0:
                        new_interval = DAY
                    else:
                        new_interval = int(round(interval * new_ease))
                next_due = now + new_interval
                new_lidx = 0

        return next_due, new_interval, new_reps, new_ease, new_lidx

    def _apply_review_to_card_sm2(self, card_id, next_due, new_interval, new_reps, new_ease, new_lidx):
        now = int(time.time())
        cur = self.db_conn.cursor()
        cur.execute("""
            UPDATE cards
            SET next_due = ?,
                interval = ?,
                reps = ?,
                ease = ?,
                learning_step_index = ?,
                last_reviewed = ?
            WHERE id = ?
        """, (next_due, new_interval, new_reps, new_ease, new_lidx, now, card_id))
        self.db_conn.commit()

    def _compute_next_for_choice(self, card_row, choice):
        now = int(time.time())
        reps = int(card_row.get("reps", 0) or 0)
        interval = int(card_row.get("interval", 0) or 0)
        ease = float(card_row.get("ease", 2.5) or 2.5)
        lstep_index = int(card_row.get("learning_step_index", 0) or 0)

        is_learning = reps == 0

        if is_learning:
            if choice == "again": # Repeat at first learning step
                next_due = now + LEARNING_STEPS[min(lstep_index, len(LEARNING_STEPS)-1)]
                new_lidx = min(lstep_index + 1, len(LEARNING_STEPS)-1)
                new_reps = reps
                new_interval = 0
            elif choice == "hard":
                next_due = now + LEARNING_STEPS[min(lstep_index, len(LEARNING_STEPS)-1)]
                new_lidx = min(lstep_index + 1, len(LEARNING_STEPS)-1)
                new_reps = reps
                new_interval = 0
            elif choice in ("good", "easy"): # Graduate to learned state
                if choice == "good":
                    new_interval = DAY
                else:
                    new_interval = 4 * DAY
                next_due = now + new_interval
                new_reps = reps + 1
                new_lidx = 0
            else:
                next_due = now + LEARNING_STEPS[0]
                new_lidx = lstep_index
                new_reps = reps
                new_interval = interval
        else:
            if choice == "again": # Put into short repeat
                next_due = now + LEARNING_STEPS[0]
                new_reps = reps
                new_interval = interval
                new_lidx = lstep_index
            elif choice == "hard":
                new_interval = max(60, int(interval * 1.2)) if interval > 0 else 10 * 60
                next_due = now + new_interval
                new_reps = reps + 1
                new_lidx = lstep_index
            elif choice == "good":
                new_interval = max(24*3600, int(max(interval, 24*3600) * 1.3))
                next_due = now + new_interval
                new_reps = reps + 1
                new_lidx = lstep_index
            elif choice == "easy":
                new_interval = max(2*24*3600, int(max(interval, 24*3600) * 2.5))
                next_due = now + new_interval
                new_reps = reps + 1
                new_lidx = lstep_index
            else:
                next_due = now + 10*60
                new_reps = reps
                new_interval = interval
                new_lidx = lstep_index
        return next_due, new_interval, new_reps, new_lidx

    def _apply_review_to_card(self, card_id, next_due, new_interval, new_reps, new_lidx):
        now = int(time.time())
        cur = self.db_conn.cursor()
        cur.execute("""
            UPDATE cards
            SET next_due = ?,
                interval = ?,
                reps = ?,
                learning_step_index = ?,
                last_reviewed = ?
            WHERE id = ?
        """, (next_due, new_interval, new_reps, new_lidx, now, card_id))
        self.db_conn.commit()


