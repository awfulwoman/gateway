from __future__ import annotations
from gateway.cli import fmt


# --- calendar ---

def test_calendar_events_empty():
    assert fmt.calendar_events([]) == "No events."


def test_calendar_events():
    events = [{"title": "Stand-up", "start": "2026-06-07 09:00:00 +0000", "calendar": "Work", "location": "", "end": "", "all_day": False, "event_id": "1", "notes": "", "url": ""}]
    out = fmt.calendar_events(events)
    assert "Stand-up" in out
    assert "Work" in out


def test_calendar_events_with_location():
    events = [{"title": "Meeting", "start": "2026-06-07 14:00:00 +0000", "calendar": "Work", "location": "Room 2B", "end": "", "all_day": False, "event_id": "2", "notes": "", "url": ""}]
    out = fmt.calendar_events(events)
    assert "Room 2B" in out


def test_calendars_empty():
    assert fmt.calendars([]) == "No calendars."


def test_calendars():
    data = [{"name": "Work", "id": "abc", "color": "blue"}, {"name": "Personal", "id": "def", "color": "red"}]
    out = fmt.calendars(data)
    assert "Work" in out
    assert "Personal" in out


# --- reminders ---

def test_reminders_empty():
    assert fmt.reminders([]) == "No reminders."


def test_reminders():
    data = [{"title": "Buy milk", "done": False, "due": "2026-06-08", "notes": "", "priority": 0, "list": "Shopping"}]
    out = fmt.reminders(data)
    assert "Buy milk" in out
    assert "Shopping" in out
    assert "[ ]" in out


def test_reminders_completed():
    data = [{"title": "Done task", "done": True, "due": None, "notes": "", "priority": 0, "list": "Inbox"}]
    out = fmt.reminders(data)
    assert "[x]" in out


def test_reminders_with_location():
    data = [{"title": "Buy eggs", "done": False, "due": None, "notes": "", "priority": 0, "list": "Reminders",
             "location": {"name": "Späti", "lat": 52.52, "lon": 13.4, "radius_m": 150, "trigger": "arrive"}}]
    out = fmt.reminders(data)
    assert "📍 Späti (arrive, 150m)" in out


# --- contacts ---

def test_contacts_empty():
    assert fmt.contacts([]) == "No contacts found."


def test_contacts():
    data = [{"name": "Alice Smith", "nickname": "", "organisation": "ACME", "job_title": "", "emails": ["alice@example.com"], "phones": ["+1 555-1234"], "addresses": [], "birthday": None, "urls": [], "note": ""}]
    out = fmt.contacts(data)
    assert "Alice Smith" in out
    assert "alice@example.com" in out
    assert "+1 555-1234" in out


# --- email ---

def test_emails_empty():
    assert fmt.emails({"messages": [], "next_cursor": None}) == "No emails."


def test_emails():
    data = {"messages": [{"id": "m1", "account": "personal", "from": "bob@example.com", "to": "me@x.com",
                           "subject": "Hello there", "date": "2026-06-07T10:00:00Z"}], "next_cursor": None}
    out = fmt.emails(data)
    assert "bob@example.com" in out
    assert "Hello there" in out


def test_emails_shows_account_column_only_when_more_than_one_is_present():
    one_account = {"messages": [
        {"id": "m1", "account": "personal", "from": "a@x.com", "subject": "A", "date": "2026-06-07T10:00:00Z"},
        {"id": "m2", "account": "personal", "from": "b@x.com", "subject": "B", "date": "2026-06-08T10:00:00Z"},
    ], "next_cursor": None}
    assert "[personal]" not in fmt.emails(one_account)

    two_accounts = {"messages": [
        {"id": "m1", "account": "personal", "from": "a@x.com", "subject": "A", "date": "2026-06-07T10:00:00Z"},
        {"id": "m2", "account": "work", "from": "b@x.com", "subject": "B", "date": "2026-06-08T10:00:00Z"},
    ], "next_cursor": None}
    out = fmt.emails(two_accounts)
    assert "[personal]" in out
    assert "[work]" in out


def test_emails_shows_a_cursor_hint_when_more_pages_remain():
    data = {"messages": [{"id": "m1", "account": "personal", "from": "a@x.com", "subject": "A",
                           "date": "2026-06-07T10:00:00Z"}], "next_cursor": "abc123"}
    assert "abc123" in fmt.emails(data)


def test_email_body():
    data = {"message_id": "<abc>", "from": "bob@example.com", "to": "me@x.com", "subject": "Hi", "date": "2026-06-07", "body": "Body text here"}
    out = fmt.email_body(data)
    assert "bob@example.com" in out
    assert "Body text here" in out


# --- notes ---

def test_notes_empty():
    assert fmt.notes([]) == "No notes."


def test_notes():
    data = ["Daily/2026-06-07.md", "Projects/Gateway.md"]
    out = fmt.notes(data)
    assert "Daily/2026-06-07.md" in out


def test_note_content():
    data = {"path": "Projects/Gateway.md", "content": "# Gateway\n\nNotes here."}
    out = fmt.note_content(data)
    assert "Gateway.md" in out
    assert "Notes here." in out


def test_note_search_results_empty():
    assert fmt.note_search_results([]) == "No matches."


def test_note_search_results():
    data = [{"path": "Projects/Gateway.md", "match_type": "content", "line": 5, "context": "some matching line"}]
    out = fmt.note_search_results(data)
    assert "Gateway.md" in out
    assert "some matching line" in out


# --- bookmarks ---

def test_bookmarks_empty():
    assert fmt.bookmarks({"bookmarks": [], "next_cursor": None}) == "No bookmarks."


def test_bookmarks():
    data = {"bookmarks": [{"id": "abc123", "title": "Python docs", "url": "https://docs.python.org", "type": "link", "tags": ["python"], "favourited": False, "archived": False, "created_at": None, "note": None, "summary": ""}], "next_cursor": None}
    out = fmt.bookmarks(data)
    assert "Python docs" in out
    assert "abc123" in out


# --- issues ---

def test_issues_empty():
    assert fmt.issues([]) == "No issues."


def test_issues():
    data = [{"id": 42, "title": "Write tests", "status": "open",
              "due": "2026-07-01", "priority": 2, "project": "Gateway", "labels": ["dev"]}]
    out = fmt.issues(data)
    assert "#42" in out
    assert "Write tests" in out
    assert "2026-07-01" in out
    assert "[Gateway]" in out


def test_issues_done():
    data = [{"id": 1, "title": "Done thing", "status": "done",
              "due": "", "priority": 0, "project": "", "labels": []}]
    out = fmt.issues(data)
    assert "[x]" in out


# --- location ---

def test_location():
    data = {"lat": 51.5074, "lon": -0.1278, "timestamp": "2026-06-07T10:30:00+00:00", "accuracy_m": 10}
    out = fmt.location(data)
    assert "51.5074" in out
    assert "-0.1278" in out


def test_location_error():
    out = fmt.location({"error": "No data"})
    assert "No data" in out


def test_location_history_empty():
    assert fmt.location_history({"count": 0, "points": []}) == "No location history."


def test_devices_empty():
    assert fmt.devices([]) == "No devices."


def test_devices():
    data = [{"user": "charlie", "devices": ["iphone", "macbook"]}]
    out = fmt.devices(data)
    assert "charlie" in out
    assert "iphone" in out


# --- reminder_lists ---

def test_reminder_lists_empty():
    assert fmt.reminder_lists([]) == "No reminder lists."


def test_reminder_lists():
    data = [{"name": "Shopping", "id": "r1"}, {"name": "Work", "id": "r2"}]
    out = fmt.reminder_lists(data)
    assert "Shopping" in out
    assert "Work" in out


# --- bookmark_detail ---

def test_bookmark_detail():
    b = {"id": "abc123", "title": "Python docs", "url": "https://docs.python.org", "tags": ["python", "docs"], "summary": "Official Python documentation", "note": "Useful reference"}
    out = fmt.bookmark_detail(b)
    assert "abc123" in out
    assert "https://docs.python.org" in out
    assert "python" in out
    assert "Useful reference" in out


# --- tags ---

def test_tags_empty():
    assert fmt.tags([]) == "No tags."


def test_tags():
    data = [{"id": "t1", "name": "python", "count": 5}, {"id": "t2", "name": "tutorial", "count": 3}]
    out = fmt.tags(data)
    assert "python" in out
    assert "5" in out


# --- lists ---

def test_lists_empty():
    assert fmt.lists([]) == "No lists."


def test_lists():
    data = [{"id": "l1", "name": "Reading", "icon": "📚", "parent_id": None}]
    out = fmt.lists(data)
    assert "Reading" in out
    assert "l1" in out


# --- issue_detail ---

def test_issue_detail():
    t = {
        "id": 42, "title": "Write tests", "status": "open",
        "due": "2026-07-01", "priority": 2, "project": "Gateway",
        "description": "Needs TDD", "labels": ["urgent"], "related": [17],
        "reminders": [], "checklist": [{"text": "Draft tests", "done": False}],
        "comments": [{"timestamp": "2026-06-16T10:00", "text": "Started"}],
    }
    out = fmt.issue_detail(t)
    assert "#42" in out
    assert "Write tests" in out
    assert "Needs TDD" in out
    assert "urgent" in out
    assert "Draft tests" in out
    assert "Started" in out
    assert "#17" in out


# --- location_history populated ---

def test_location_history_populated():
    data = {"count": 2, "points": [
        {"lat": 51.5074, "lon": -0.1278, "timestamp": "2026-06-07T09:00:00+00:00"},
        {"lat": 51.51, "lon": -0.12, "timestamp": "2026-06-07T10:30:00+00:00"},
    ]}
    out = fmt.location_history(data)
    assert "Count: 2" in out
    assert "51.5074" in out
