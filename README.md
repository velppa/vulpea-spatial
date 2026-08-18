# vulpea-spatial

Spatial canvas for [vulpea](https://github.com/d12frosted/vulpea) notes in Emacs.
It turns a vulpea notes directory into a draggable, resizeable
spatial canvas of images, pdfs, videos, and notes, opened in your browser.

A fork of [denote-spatial](https://github.com/SenkiReign/denote-spatial).
Notes, tags, and the `[[id:...]]` link graph are read from the vulpea
database (`vulpea-db-autosync-mode` keeps it fresh); note files are read
only for card snippets, and media files are picked up by a directory
scan.

The only external dependency is `python3`.

## Features

- Grid, feed, cluster, and keyword views
- Drag and resize cards, alone or as a group
- Cluster mode groups linked notes together
- Click an `id:` link to jump straight to that note
- Links to heading-level notes resolve to their file's card
- Images, videos, and pdfs supported
- Search / regex filter
- Layout is saved locally, notes are never modified
- Ctrl + wheel to zoom in/out

## Setup

Copy `vulpea-spatial.el`, `server.py`, and `index.html` into one folder
(e.g. `~/.emacs.d/lisp/vulpea-spatial/`).

```elisp
(add-to-list 'load-path "/path/to/this/folder")
(require 'vulpea-spatial)
(setq vulpea-spatial-notes-directory "~/Notes")
```

When `vulpea-spatial-notes-directory` is nil, the first entry of
`vulpea-db-sync-directories` is used.  The database defaults to
`vulpea-db-location` (`vulpea-spatial-db` overrides it).

## Usage

```
M-x vulpea-spatial-open
M-x vulpea-spatial-stop
```
