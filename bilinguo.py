#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
bilinguo.py - Final Version
Vocabulary Manager with PySide6 + SQLite
"""

import os, sys, json, csv, re, sqlite3, threading
from datetime import datetime

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, QObject, Signal
except Exception:
    raise SystemExit("PySide6 not installed. Install: pip install PySide6 requests")

import requests

DB_PATH = "vocab.db"
DEFAULT_LIBRE_URL = "https://api.mymemory.translated.net/get"

# -------------------------
# Database helpers
# -------------------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute('''
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE,
    translations TEXT DEFAULT '',
    added_at TEXT,
    anki_created INTEGER DEFAULT 0
)
''')
conn.commit()

def normalize_word(w: str) -> str:
    w = w.strip()
    w = w.replace("’", "'").replace("“", '"').replace("”", '"')
    w = re.sub(r'^[^\w\']+|[^\w\']+$', '', w, flags=re.UNICODE)
    return w.lower()

def tokenize_text_to_unique_words(text: str, min_len: int = 2):
    tokens = re.findall(r"[A-Za-z]+", text)
    out = set()
    for t in tokens:
        n = normalize_word(t)
        if len(n) >= min_len:
            out.add(n)
    return sorted(out)

def db_add_or_update_word(word: str, translation: str = ""):
    if not word: return
    wk = word.strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur.execute("SELECT translations FROM words WHERE word = ?", (wk,))
        row = cur.fetchone()
        if row:
            existing = row[0] or ""
            parts = [p for p in existing.split(" | ") if p]
            if translation and translation not in parts:
                parts.append(translation)
                new_trans = " | ".join(parts)
                cur.execute("UPDATE words SET translations = ?, anki_created = 0 WHERE word = ?", (new_trans, wk))
        else:
            cur.execute("INSERT INTO words (word, translations, added_at) VALUES (?, ?, ?)", (wk, translation or "", timestamp))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

def db_get_all():
    cur.execute("SELECT id, word, translations, added_at, anki_created FROM words ORDER BY word COLLATE NOCASE")
    return cur.fetchall()

def db_get_stats():
    cur.execute("SELECT COUNT(*) FROM words")
    total_words = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM words WHERE anki_created = 1")
    anki_created = cur.fetchone()[0]
    
    return total_words, anki_created

def db_delete_words(ids):
    if not ids: return
    cur.execute(f"DELETE FROM words WHERE id IN ({','.join(['?']*len(ids))})", ids)
    conn.commit()

def db_set_anki_created_for_word(word):
    cur.execute("UPDATE words SET anki_created = 1 WHERE word = ?", (word,))
    conn.commit()

def db_reset_anki_flags():
    cur.execute("UPDATE words SET anki_created = 0")
    conn.commit()

def db_update_translations_for_id(rowid, translations_text):
    cur.execute("SELECT word, translations FROM words WHERE id = ?", (rowid,))
    r = cur.fetchone()
    if not r: return
    word = r[0]
    existing = r[1] or ""
    parts = [p for p in existing.split(" | ") if p]
    new_parts = [p.strip() for p in translations_text.split("|") if p.strip()]
    changed = False
    for np in new_parts:
        if np not in parts:
            parts.append(np)
            changed = True
    new_trans = " | ".join(parts)
    if new_trans != existing:
        cur.execute("UPDATE words SET translations = ?, anki_created = 0 WHERE id = ?", (new_trans, rowid))
        conn.commit()

# -------------------------
# Translation
# -------------------------
def translate_online_mymemory(word, source="en", target="fa", timeout=10):
    try:
        payload = {"q": word, "langpair": f"{source}|{target}"}
        r = requests.get(DEFAULT_LIBRE_URL, params=payload, timeout=timeout)
        if r.status_code == 200:
            j = r.json()
            if "responseData" in j and "translatedText" in j["responseData"]:
                tr = j["responseData"]["translatedText"]
                if tr and tr != word:
                    return tr
    except Exception as e:
        print(f"Translation error: {e}")
        return None
    return None

# -------------------------
# Qt Application
# -------------------------
class TranslationManager(QObject):
    finished = Signal(str, str, bool)
    
    def __init__(self):
        super().__init__()
        
    def translate(self, word, src, tgt):
        try:
            tr = translate_online_mymemory(word, src, tgt)
            if tr:
                db_add_or_update_word(word, tr)
                self.finished.emit(word, tr, True)
            else:
                self.finished.emit(word, "", False)
        except Exception as e:
            print(f"Translation error: {e}")
            self.finished.emit(word, "", False)

class VocabWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bilinguo Vocabulary Manager")
        self.resize(900, 700)
        self.source_lang = "en"
        self.target_lang = "fa"
        self.translation_manager = TranslationManager()
        self._setup_ui()
        self.refresh_table()

    def _setup_ui(self):
        w = QtWidgets.QWidget()
        self.setCentralWidget(w)
        layout = QtWidgets.QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Top row - Import buttons (exactly as in the image)
        top_row = QtWidgets.QHBoxLayout()
        
        btn_import_json = QtWidgets.QPushButton("Import JSON")
        btn_import_json.clicked.connect(self.import_json)
        top_row.addWidget(btn_import_json)
        
        btn_import_text = QtWidgets.QPushButton("Import TEXT")
        btn_import_text.clicked.connect(self.import_text)
        top_row.addWidget(btn_import_text)
        
        btn_help = QtWidgets.QPushButton("Help")
        btn_help.clicked.connect(self.show_help)
        top_row.addWidget(btn_help)
        
        btn_about = QtWidgets.QPushButton("About")
        btn_about.clicked.connect(self.show_about)
        top_row.addWidget(btn_about)
        
        top_row.addStretch()
        layout.addLayout(top_row)

        # Table - Main content area
        self.table = QtWidgets.QTableView()
        self.table.setMinimumHeight(300)
        
        self.model = QtGui.QStandardItemModel(0, 4)
        self.model.setHorizontalHeaderLabels(["Word", "Translations", "Added At", "Anki"])
        self.table.setModel(self.model)
        
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        
        # Set column widths
        self.table.setColumnWidth(0, 120)  # Word
        self.table.setColumnWidth(1, 250)  # Translations
        self.table.setColumnWidth(2, 150)  # Added At
        self.table.setColumnWidth(3, 60)   # Anki
        
        layout.addWidget(self.table, 1)

        # Middle row - Export buttons (exactly as in the image)
        middle_row = QtWidgets.QHBoxLayout()
        
        btn_export = QtWidgets.QPushButton("Export CSV for Anki")
        btn_export.clicked.connect(self.export_anki_dialog)
        middle_row.addWidget(btn_export)
        
        btn_reset = QtWidgets.QPushButton("Reset Anki Flags")
        btn_reset.clicked.connect(self.reset_anki_flags)
        middle_row.addWidget(btn_reset)
        
        btn_delete = QtWidgets.QPushButton("Delete Selected")
        btn_delete.clicked.connect(self.delete_selected)
        middle_row.addWidget(btn_delete)
        
        middle_row.addStretch()
        layout.addLayout(middle_row)

        # Separator line (exactly as in the image)
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)

        # Bottom section - Word details (exactly as in the image)
        # Selected word row
        selected_row = QtWidgets.QHBoxLayout()
        selected_row.addWidget(QtWidgets.QLabel("Selected word:"))
        self.lbl_selected_word = QtWidgets.QLabel("-")
        self.lbl_selected_word.setStyleSheet("font-weight: bold;")
        selected_row.addWidget(self.lbl_selected_word)
        selected_row.addStretch()
        layout.addLayout(selected_row)

        # Translations row
        trans_row = QtWidgets.QHBoxLayout()
        trans_row.addWidget(QtWidgets.QLabel("Translations (I separated):"))
        self.txt_translations = QtWidgets.QPlainTextEdit()
        self.txt_translations.setMaximumHeight(60)
        trans_row.addWidget(self.txt_translations, 1)
        layout.addLayout(trans_row)

        # Language selection and action buttons row
        action_row = QtWidgets.QHBoxLayout()
        
        # Language inputs
        action_row.addWidget(QtWidgets.QLabel("Source:"))
        self.edit_src = QtWidgets.QLineEdit(self.source_lang)
        self.edit_src.setMaximumWidth(40)
        action_row.addWidget(self.edit_src)
        
        action_row.addWidget(QtWidgets.QLabel("Target:"))
        self.edit_tgt = QtWidgets.QLineEdit(self.target_lang)
        self.edit_tgt.setMaximumWidth(40)
        action_row.addWidget(self.edit_tgt)
        
        # Buttons
        btn_translate = QtWidgets.QPushButton("Translate Selected")
        btn_translate.clicked.connect(self.translate_selected_online)
        action_row.addWidget(btn_translate)
        
        btn_refresh = QtWidgets.QPushButton("Refresh Table")
        btn_refresh.clicked.connect(self.refresh_table)
        action_row.addWidget(btn_refresh)
        
        action_row.addStretch()
        layout.addLayout(action_row)

        # Stats and Save button row
        bottom_row = QtWidgets.QHBoxLayout()
        
        self.lbl_stats = QtWidgets.QLabel("Words: 0 | Flashcards: 0")
        bottom_row.addWidget(self.lbl_stats)
        
        bottom_row.addStretch()
        
        btn_save = QtWidgets.QPushButton("Save edits")
        btn_save.clicked.connect(self.save_edits)
        bottom_row.addWidget(btn_save)
        
        layout.addLayout(bottom_row)

        # Progress bar
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Connections
        self.table.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.table.doubleClicked.connect(self.on_table_double_click)
        self.translation_manager.finished.connect(self.on_translation_finished)

    def refresh_table(self):
        self.model.removeRows(0, self.model.rowCount())
        rows = db_get_all()
        for r in rows:
            rowid, word, translations, added_at, anki = r
            it_word = QtGui.QStandardItem(word)
            it_trans = QtGui.QStandardItem(translations)
            it_added = QtGui.QStandardItem(added_at)
            it_anki = QtGui.QStandardItem("Yes" if anki else "No")
            
            it_word.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            it_trans.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            it_added.setTextAlignment(Qt.AlignCenter)
            it_anki.setTextAlignment(Qt.AlignCenter)
            
            self.model.appendRow([it_word, it_trans, it_added, it_anki])
        
        self.table.resizeColumnsToContents()
        self.update_stats()

    def update_stats(self):
        total_words, anki_created = db_get_stats()
        self.lbl_stats.setText(f"Words: {total_words} | Flashcards: {anki_created}")

    def on_selection_changed(self, selected, deselected):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            self.lbl_selected_word.setText("-")
            self.txt_translations.setPlainText("")
            return
            
        index = sel[0]
        word = self.model.item(index.row(), 0).text()
        translations = self.model.item(index.row(), 1).text()
        
        self.lbl_selected_word.setText(word)
        self.txt_translations.setPlainText(translations or "")

    def on_table_double_click(self, idx):
        self.on_selection_changed(None, None)
        self.txt_translations.setFocus()

    def save_edits(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Save", "Please select a word first.")
            return
            
        index = sel[0]
        word = self.model.item(index.row(), 0).text()
        translations_text = self.txt_translations.toPlainText().strip()
        
        # Find the word ID from database
        cur.execute("SELECT id FROM words WHERE word = ?", (word,))
        result = cur.fetchone()
        if result:
            rowid = result[0]
            db_update_translations_for_id(rowid, translations_text)
            QtWidgets.QMessageBox.information(self, "Save", "Changes saved successfully.")
            self.refresh_table()

    def import_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open JSON", "", "JSON Files (*.json);;All Files (*)")
        if not path: return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if not isinstance(data, list):
                QtWidgets.QMessageBox.warning(self, "Import JSON", "JSON file must contain a list of objects.")
                return
                
            count = 0
            for item in data:
                if isinstance(item, dict) and "word" in item:
                    w = item.get("word", "").strip()
                    tr = item.get("translation", "").strip()
                    if w:
                        db_add_or_update_word(w, tr)
                        count += 1
                        
            QtWidgets.QMessageBox.information(self, "Import JSON", f"Successfully imported {count} entries.")
            self.refresh_table()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Import JSON", f"Error: {str(e)}")

    def import_text(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Text", "", "Text Files (*.txt *.md *.csv);;All Files (*)")
        if not path: return
        
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
                
            words = tokenize_text_to_unique_words(txt, min_len=2)
            for w in words:
                db_add_or_update_word(w, "")
                
            QtWidgets.QMessageBox.information(self, "Import Text", f"Found and added {len(words)} unique words.")
            self.refresh_table()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Import Text", f"Error: {str(e)}")

    def translate_selected_online(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Translate", "Please select a word first.")
            return
            
        index = sel[0]
        word = self.model.item(index.row(), 0).text()
        src = self.edit_src.text() or "en"
        tgt = self.edit_tgt.text() or "fa"
        
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        
        thread = threading.Thread(target=self.translation_manager.translate, args=(word, src, tgt))
        thread.daemon = True
        thread.start()

    def on_translation_finished(self, word, translation, success):
        self.progress.setVisible(False)
        if success:
            self.refresh_table()
            QtWidgets.QMessageBox.information(self, "Translation", f"Translated '{word}' successfully.")
        else:
            QtWidgets.QMessageBox.warning(self, "Translation", f"Failed to translate '{word}'. Please check your internet connection.")

    def export_anki_dialog(self):
        num, ok = QtWidgets.QInputDialog.getInt(self, "Export", "How many flashcards to export?", 50, 1, 10000)
        if not ok: return
        self.export_anki(num)

    def export_anki(self, limit):
        cur.execute("SELECT word, translations FROM words WHERE anki_created=0 LIMIT ?", (limit,))
        rows = cur.fetchall()
        
        if not rows:
            QtWidgets.QMessageBox.information(self, "Export", "No new words available for export.")
            return
            
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save CSV", "anki_cards.csv", "CSV Files (*.csv);;All Files (*)")
        if not path: return
        
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Front", "Back"])
                for w, tr in rows:
                    writer.writerow([w, tr])
                    db_set_anki_created_for_word(w)
                    
            QtWidgets.QMessageBox.information(self, "Export", f"Successfully exported {len(rows)} cards to {path}")
            self.refresh_table()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export", f"Error: {str(e)}")

    def reset_anki_flags(self):
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Anki Flags", 
            "Are you sure you want to reset Anki flags for ALL words?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            db_reset_anki_flags()
            QtWidgets.QMessageBox.information(self, "Reset", "All Anki flags have been reset.")
            self.refresh_table()

    def delete_selected(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QtWidgets.QMessageBox.warning(self, "Delete", "Please select words to delete first.")
            return
        
        # Confirm deletion
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete {len(sel)} selected word(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Get words from selected rows
            words_to_delete = []
            for index in sel:
                word = self.model.item(index.row(), 0).text()
                words_to_delete.append(word)
            
            # Get IDs from database
            placeholders = ','.join(['?'] * len(words_to_delete))
            cur.execute(f"SELECT id FROM words WHERE word IN ({placeholders})", words_to_delete)
            ids = [str(row[0]) for row in cur.fetchall()]
            
            if ids:
                db_delete_words(ids)
                QtWidgets.QMessageBox.information(self, "Delete", f"Deleted {len(ids)} word(s).")
                self.refresh_table()

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self, "About", 
            "Bilinguo Vocabulary Manager\n\n"
            "A tool for managing vocabulary words and translations.\n\n"
            "https://biabani.github.io/"

        )

    def show_help(self):
        help_text = """
Help Guide:

1. IMPORT:
   - Use 'Import JSON' for structured word lists with translations
   - Use 'Import TEXT' to extract words from documents

2. TRANSLATION:
   - Select a word from the table
   - Click 'Translate Selected' to get translation
   - Edit translations manually in the text box
   - Click 'Save edits' to save changes

3. EXPORT:
   - Use 'Export CSV for Anki' to create flashcards
   - Use 'Reset Anki Flags' to mark all words for re-export

4. MANAGEMENT:
   - Select words and click 'Delete Selected' to remove them
   - Table is sortable by clicking column headers

Note: Internet connection required for translation.
"""
        QtWidgets.QMessageBox.information(self, "Help", help_text)

# -------------------------
# Main
# -------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    win = VocabWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
