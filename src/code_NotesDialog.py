# Reusable plain-text notes editor popup, and the helper used to clip notes
# text to a fixed number of display lines (with a trailing ellipsis) wherever
# notes are shown read-only, e.g. the Enlargement details panes.

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
)
from PySide6.QtCore import Qt


class NotesDialog(QDialog):
    """Small popup (styled like ChecklistTreeDialog) holding a single plain-text
    box.  After exec(), `result` is None (cancelled) or the edited text."""

    def __init__(self, initialText="", parent=None):
        super().__init__(parent)
        self.result = None

        self.setWindowTitle("Notes")
        self.resize(420, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.textEdit = QPlainTextEdit()
        self.textEdit.setPlainText(initialText)
        # Notes are plain text only — paste should not carry in rich formatting.
        layout.addWidget(self.textEdit)

        btnRow = QHBoxLayout()
        btnRow.setSpacing(10)
        btnRow.addStretch()
        btnCancel = QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        btnRow.addWidget(btnCancel)
        btnOK = QPushButton("OK")
        btnOK.setDefault(True)
        btnOK.clicked.connect(self._accept)
        btnRow.addWidget(btnOK)
        layout.addLayout(btnRow)

        self.textEdit.setFocus()

    def _accept(self):
        self.result = self.textEdit.toPlainText()
        self.accept()


def elideToLines(text, metrics, maxWidth, maxLines=4):
    """Word-wrap `text` against `maxWidth` (using QFontMetrics `metrics`),
    truncated to at most `maxLines` lines.  If the text overflows maxLines,
    the last shown line is trimmed and given a trailing ellipsis."""
    if not text:
        return ""

    # Collapse any embedded newlines (e.g. notes pasted from a source that
    # hard-wrapped its lines) so this preview always re-flows as one
    # continuous paragraph rather than stranding a leftover word alone on
    # its own line at each embedded break.
    text = " ".join(text.split())

    # Pack lines a few px under the caller's maxWidth, not right up against
    # it. The greedy packer below accepts a word whenever the running line's
    # horizontalAdvance() is still <= the target width, so on a line that
    # saturates the target it can land with zero px of margin — and the
    # label's actual text layout can then render a hair wider than
    # horizontalAdvance() predicted, clipping the last character at the
    # label's edge. This keeps every line safely inside maxWidth regardless
    # of exactly which words happen to fill it.
    packWidth = max(1, maxWidth - 4)

    def hardBreak(word, lines):
        """A single word wider than packWidth on its own — break it character
        by character (e.g. a long pasted URL) rather than let it overflow."""
        chunk = ""
        for ch in word:
            trial = chunk + ch
            if metrics.horizontalAdvance(trial) <= packWidth or not chunk:
                chunk = trial
            else:
                lines.append(chunk)
                chunk = ch
        return chunk

    lines = []
    current = ""
    for word in text.split(" "):
        trial = (current + " " + word).strip() if current else word
        if metrics.horizontalAdvance(trial) <= packWidth:
            current = trial
            continue
        if current:
            lines.append(current)
        if metrics.horizontalAdvance(word) <= packWidth:
            current = word
        else:
            current = hardBreak(word, lines)
        if len(lines) > maxLines:
            break
    lines.append(current)

    if len(lines) <= maxLines:
        return "\n".join(lines)

    shown = lines[:maxLines]
    last = shown[-1]
    while last and metrics.horizontalAdvance(last + "…") > packWidth:
        last = last[:-1].rstrip()
    shown[-1] = last + "…"
    return "\n".join(shown)
