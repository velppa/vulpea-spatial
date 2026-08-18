;;; vulpea-spatial.el --- A canvas for vulpea -*- lexical-binding: t; -*-

;; Author:  Pavel Popov
;; Keywords: emacs, vulpea, notes, multimedia, moodboard
;; Package-Requires: ((emacs "27.1"))
;; Version: 0.1.0

;;; Commentary:

;; vulpea-spatial.el turns a vulpea notes directory into a
;; draggable, resizeable spatial canvas of images, pdfs, videos, and notes opened in your browser.
;;
;; The only external dependency is `python3'.
;;
;; Setup:
;;   (add-to-list 'load-path "/path/to/this/folder")
;;   (require 'vulpea-spatial)
;;   (setq vulpea-spatial-notes-directory "~/Notes")
;;;
;; Usage:
;;   M-x vulpea-spatial-open   ; starts the server (if needed) + opens browser
;;   M-x vulpea-spatial-stop   ; stops the server

;;; Code:

(defgroup vulpea-spatial nil
  "Local spatial canvas for vulpea notes, images, and videos."
  :group 'convenience
  :prefix "vulpea-spatial-")

(defcustom vulpea-spatial-notes-directory nil
  "Directory of vulpea notes/images/videos to browse spatially.
If nil, `vulpea-spatial-open' first tries the first entry of
`vulpea-db-sync-directories' (if the `vulpea' package is loaded and
configured), then falls back to prompting once and remembering it for
the session."
  :type '(choice (const :tag "Use vulpea-db-sync-directories / ask" nil) directory)
  :group 'vulpea-spatial)

(defcustom vulpea-spatial-port 8420
  "Local port the vulpea-spatial server listens on (localhost only)."
  :type 'integer
  :group 'vulpea-spatial)

(defcustom vulpea-spatial-python-executable "python3"
  "Python 3 executable used to run the local server."
  :type 'string
  :group 'vulpea-spatial)

(defcustom vulpea-spatial-db nil
  "Path to the vulpea database the server reads notes from.
If nil, `vulpea-spatial-open' uses `vulpea-db-location'."
  :type '(choice (const :tag "Use vulpea-db-location" nil) file)
  :group 'vulpea-spatial)

(defvar vulpea-spatial--process nil
  "The running vulpea-spatial server process, if any.")

(defvar vulpea-spatial--dir
  (file-name-directory
   (or load-file-name
       (and byte-compile-current-file (bound-and-true-p byte-compile-current-file))
       (buffer-file-name)))
  "Directory where `vulpea-spatial.el' lives (captured at load time).")

(defun vulpea-spatial--package-directory ()
  "Directory this file (and its bundled server.py/index.html) lives in."
  (or vulpea-spatial--dir
      (file-name-directory (locate-library "vulpea-spatial"))))

(defun vulpea-spatial--server-script ()
  "Path to the bundled server.py."
  (expand-file-name "server.py" (vulpea-spatial--package-directory)))

(defun vulpea-spatial-export-html (path)
  "Export the org file at PATH to body-only HTML.
Write the result to a temp file and return that file's name.
=[[id:...]]= links become canvas links handled by the frontend."
  (let ((out (make-temp-file "vulpea-spatial-" nil ".html")))
    (with-temp-buffer
      (insert-file-contents path)
      (delay-mode-hooks (org-mode))
      (goto-char (point-min))
      (while (re-search-forward
              "\\[\\[id:\\([^][]+\\)\\]\\(?:\\[\\([^][]*\\)\\]\\)?\\]" nil t)
        (let ((id (match-string 1)))
          (replace-match
           (format "@@html:<a class=\"id-link\" onclick=\"handleIdLinkClick(event, '%s')\">%s</a>@@"
                   id (or (match-string 2) id))
           t t)))
      (let ((org-export-use-babel nil)
            (org-export-with-broken-links t))
        (write-region (org-export-as 'html nil nil t) nil out nil 'quiet)))
    out))

;;;###autoload
(defun vulpea-spatial-open ()
  "Start the vulpea-spatial server if needed, then open it in your browser.
If it's already running, just reopens the browser tab."
  (interactive)
  (unless (executable-find vulpea-spatial-python-executable)
    (user-error "vulpea-spatial: `%s' not found — Python 3 is the only dependency"
                vulpea-spatial-python-executable))
  (unless (file-exists-p (vulpea-spatial--server-script))
    (user-error "vulpea-spatial: server.py not found next to vulpea-spatial.el"))
  (unless vulpea-spatial-notes-directory
    (setq vulpea-spatial-notes-directory
          (or (and (boundp 'vulpea-db-sync-directories)
                   (car vulpea-db-sync-directories))
              (read-directory-name "Notes directory for vulpea-spatial: "))))
  (let ((url (format "http://localhost:%d" vulpea-spatial-port))
        (db (or vulpea-spatial-db
                (and (boundp 'vulpea-db-location) vulpea-db-location)
                "~/.config/emacs/vulpea.db")))
    (if (and vulpea-spatial--process (process-live-p vulpea-spatial--process))
        (browse-url url)
      (let ((process-environment (cons "VULPEA_SPATIAL_NO_OPEN=1" process-environment)))
        (setq vulpea-spatial--process
              (start-process "vulpea-spatial" "*vulpea-spatial*"
                              vulpea-spatial-python-executable
                              (vulpea-spatial--server-script)
                              (expand-file-name vulpea-spatial-notes-directory)
                              (number-to-string vulpea-spatial-port)
                              (expand-file-name db))))
      (message "vulpea-spatial: starting…")
      ;; give the server a beat to bind the port before we open the browser
      (run-at-time 0.8 nil (lambda () (browse-url url))))))

;;;###autoload
(defun vulpea-spatial-stop ()
  "Stop the vulpea-spatial server."
  (interactive)
  (if (and vulpea-spatial--process (process-live-p vulpea-spatial--process))
      (progn (delete-process vulpea-spatial--process)
             (setq vulpea-spatial--process nil)
             (message "vulpea-spatial: stopped"))
    (message "vulpea-spatial: not running")))

(provide 'vulpea-spatial)
;;; vulpea-spatial.el ends here
