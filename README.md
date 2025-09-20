# Bilingual Vocabulary Manager

A desktop application for managing vocabulary words with bilingual support (English-Persian) and Anki integration.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![PySide6](https://img.shields.io/badge/PySide6-GUI%20Framework-green)
![SQLite](https://img.shields.io/badge/SQLite-Database-lightgrey)

## ✨ Features

- 📥 **Import words** from JSON and TEXT files
- 🌐 **Online translation** using MyMemory API
- 💾 **SQLite database** storage
- 📊 **Advanced management** with search and sorting
- 📤 **Anki export** in CSV format
- 🎯 **Beautiful and intuitive** GUI
- 🔄 **Flashcard status** synchronization

## 📦 Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Install Dependencies

```bash
# Clone the repository
git clone https://github.com/biabani/bilinguo.git
cd bilinguo
```

### Install requirements
```
pip install -r requirements.txt
```
### Run the Application

```bash
python bilinguo.py
```

## 🚀 Usage

### Importing Words
#### 1.From JSON File:

Required format: Array of objects with word and translation fields

```
json
[
  {"word": "hello", "translation": "سلام"},
  {"word": "world", "translation": "دنیا"}
]
```
#### 2. From TEXT File:

Automatically extracts English words from text documents

### Automatic Translation
1.Select a word from the table

2.Click "Translate Selected"

3.Translation is automatically fetched and saved

### Anki Export
1.Click "Export CSV for Anki"

2.Select the number of flashcards to export

3.Import the generated CSV file into Anki

