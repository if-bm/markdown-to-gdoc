# Markdown Meeting Notes → Google Doc (Google Docs API)

This project converts markdown meeting notes into a formatted Google Doc using the Google Docs API.

## What it does

- Creates a new Google Doc programmatically
- Applies heading styles (H1/H2/H3)
- Keeps nested bullet hierarchy with indentation
- Converts markdown tasks (`- [ ]`) into a Google Docs checklist style
- Styles assignee mentions like `@sarah` (bold)
- Formats the footer lines in a distinct style

## Files

- `meeting_notes.md` — sample input (provided in the prompt)
- `markdown_to_gdoc.py` — parser + Google Docs API writer
- `colab_notebook.ipynb` — runnable notebook in Google Colab

## Requirements

- Google Colab (recommended)
- Google Docs API enabled in your Google account (Colab auth handles the credentials)
- Python packages:
  - `google-api-python-client`
  - `google-auth`

> In Colab, the notebook installs these automatically.

## Run in Google Colab

1. Open `colab_notebook.ipynb` in Colab.
2. Run cells top to bottom.
3. When prompted, sign in and allow access.
4. The notebook prints the created Google Doc link.

## Notes

- Horizontal rules (`---`) are rendered as a spacer line.
- The checklist uses the Docs API checklist bullet preset.
