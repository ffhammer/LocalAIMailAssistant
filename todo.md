# MailDb Status

- improve mailbox status to save mailboxes
- update status after/during sync
- Make this reachable via endpoint

# Sync

- write tests
- fetch hihest uid
- try it out on real mailbox

# Background Manager

- inlcude sync in loop if not done recently
- add event bus posts

# Flags

- toggle flags could overwrite other changes at the moment from other clients should fetch first.
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

## Tests

make llm part testing better. check if jobs suceed and not just fail
