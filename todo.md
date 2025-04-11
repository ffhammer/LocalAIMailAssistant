# MailDb Status

- improve mailbox status to save mailboxes
- update status after/during sync
- Make this reachable via endpoint

# Sync

- write tests
- try it out on real mailbox

# Background Manager

- inlcude sync in loop if not done recently
- add event bus posts

# Flags

- write an endpoint to update flags
- update the get mail from imap such mails are initialiazed with correct flags
- write tests

# Mailboxes

- imap code to create new mailboxes/delete
- move to mailbox
- tests

# Summaries

- include summaries to include tags

## Tags

- introduce new data model
- endpoint to update/add/remove tags
