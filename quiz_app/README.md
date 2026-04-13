# Quiz Generation and Exam Simulation System

## Features
- EPUB chapter extraction with `ebooklib` + `BeautifulSoup`
- Scripture-style true/false MCQ generation with source traceability
- Chapter quiz variant generation (5 variants x 5 questions)
- Exam variant generation (default 6 variants x 120 questions)
- Test mode and exam mode runtime behavior
- Negative marking (`+1 / -1 / 0`)
- JSON data storage
- Streamlit web interface

## Project Structure

- quiz_app/data
- quiz_app/generator
- quiz_app/engine
- quiz_app/ui
- quiz_app/main.py

## Install

```bash
pip install -r requirements.txt
```

## CLI Usage

```bash
python main.py /path/to/book.epub --seed 42
```

Generated files:
- data/chapters.json
- data/questions.json
- data/quiz_variants.json
- data/exam_variants.json

## Streamlit Usage

```bash
streamlit run ui/streamlit_app.py
```
