import html
import unicodedata


def clean_email_content(text):
    """
    Cleans email content by removing non-printable characters (except emojis),
    replacing problematic characters, decoding HTML entities, normalizing Unicode,
    and collapsing excessive whitespace.
    """

    def remove_non_printable(text):
        # Remove non-printable characters, but allow emojis and printable Unicode
        return "".join(
            char if char.isprintable() or char in {"\n", "\t", "\r"} else "�"
            for char in text
        )

    def replace_problematic_chars(text):
        # Replace specific problematic Unicode characters
        replacements = {
            "\ufffc": "",  # Object Replacement Character
            "\ufffd": "",  # Replacement Character
            "\u2028": "\n",  # Line Separator
            "\u200d": "",  # Zero Width Joiner
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    def decode_html_entities(text):
        # Decode HTML entities into plain text
        return html.unescape(text)

    def normalize_unicode(text):
        # Normalize the text to a standard Unicode form
        return unicodedata.normalize("NFC", text)

    # Step 1: Remove non-printable characters
    text = remove_non_printable(text)
    # Step 2: Replace problematic characters
    text = replace_problematic_chars(text)
    # Step 3: Decode HTML entities
    text = decode_html_entities(text)
    # Step 4: Normalize Unicode
    text = normalize_unicode(text)

    return text
