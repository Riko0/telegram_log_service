import html


def escape_html(text) -> str:
    """Escape text for Telegram HTML parse mode."""
    if text is None:
        return ""
    return html.escape(str(text))
