import curses
from datetime import timedelta, datetime
from src.mail_db import MailDB, ProccesedMailMessage
from src.accounts_loading import load_accounts
from src.ollama import summarize_email


def wrap_text(text, max_width):
    """
    Wraps text to fit within the given width, breaking lines at whitespace where possible.
    """
    
    
    lines = text.splitlines()
    newlines = []
    
    while lines:
        line = lines.pop(0)
        if len(line) < max_width:
            newlines.append(line)
            continue
        line : list[str]
        
        i = max_width -1 
        while i > 0 and not line[i].isspace():
            i -= 1
        
        cutoff = i - 1 if i > 0 else max_width -1
        newlines.append(line[:cutoff]) # excludes white space
        lines.insert(0,line[cutoff + 1:]) # skips the original one
            
            
    return newlines

def display_email_content(stdscr, email: ProccesedMailMessage):
    max_width = curses.COLS - 1
    max_height = curses.LINES - 6

    # Header
    stdscr.clear()
    stdscr.addstr(0, 0, f"From: {email.Sender}")
    stdscr.addstr(1, 0, f"Date: {email.Date_Received}")
    stdscr.addstr(2, 0, f"Subject: {email.Subject}")
    stdscr.addstr(3, 0, '-' * max_width)

    # Clean and wrap content
    wrapped_lines = wrap_text(email.Content, max_width)

    # Scrolling variables
    top_line = 0
    while True:
        # Display visible content
        stdscr.clear()
        stdscr.addstr(0, 0, f"From: {email.Sender}")
        stdscr.addstr(1, 0, f"Date: {email.Date_Received}")
        stdscr.addstr(2, 0, f"Subject: {email.Subject}")
        stdscr.addstr(3, 0, '-' * max_width)

        for i, line in enumerate(wrapped_lines[top_line:top_line + max_height]):
            stdscr.addstr(4 + i, 0, line)

        stdscr.addstr(curses.LINES - 2, 0, '-' * max_width)
        stdscr.addstr(curses.LINES - 1, 0, "Press 'b' to go back. Use UP/DOWN to scroll.")
        stdscr.refresh()

        # Handle input
        key = stdscr.getch()
        if key == ord('b'):
            break
        elif key == curses.KEY_UP and top_line > 0:
            top_line -= 1
        elif key == curses.KEY_DOWN and top_line + max_height < len(wrapped_lines):
            top_line += 1

def display_email_list(stdscr, emails : list[ProccesedMailMessage]):
    curses.curs_set(0)
    current_row = 0

    while True:
        stdscr.clear()

        # Display the list of emails
        for idx, email in enumerate(emails):
            x = 0
            y = idx
            if idx == current_row:
                stdscr.attron(curses.color_pair(1))
                stdscr.addstr(
                    y, x, f"{email.Date_Received.strftime('%Y-%m-%d')} | {email.Sender} | {email.Subject}"
                )
                stdscr.attroff(curses.color_pair(1))
            else:
                stdscr.addstr(
                    y, x, f"{email.Date_Received.strftime('%Y-%m-%d')} | {email.Sender} | {email.Subject}"
                )

        stdscr.refresh()

        # Handle keyboard input
        key = stdscr.getch()

        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(emails) - 1:
            current_row += 1
        elif key == ord("\n"):
            display_email_content(stdscr, emails[current_row])
        elif key == ord("q"):
            break

    
def setup(stdscr, emails : list[ProccesedMailMessage]):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
    display_email_list(stdscr, emails)

settings = load_accounts("secrets/accounts.yaml")["uni"]
db = MailDB("db", settings)
emails = db.load_all_inbox_mails(datetime.now() - timedelta(12))
curses.wrapper(lambda stdscr: setup(stdscr, emails))
