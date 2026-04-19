# Email Invites, Import & RSVP

Requires `msmtp`. Set organizer in `~/.config/vcal/config.toml`:

```toml
[user]
email = "user@example.com"
name = "User Name"
```

```bash
# Send invite
calendar-cli invite -s "Review" --start "2025-04-01 14:00" --timezone Europe/Berlin \
  -d 90 -a "john@example.com,Jane <jane@example.com>" --organizer-email "me@example.com"

# Export email to file instead of sending (or - for stdout)
calendar-cli invite ... --output-email invite.eml
calendar-cli invite ... --output-ics meeting.ics

# Import — handles all incoming calendar emails:
#   new invites, attendee responses, and cancellations
calendar-cli import meeting.ics
cat email.eml | calendar-cli import

# RSVP (respond to invites you received)
cat email.eml | calendar-cli reply accept
cat email.eml | calendar-cli reply decline -c "Sorry, conflict"
cat email.eml | calendar-cli reply tentative
```
