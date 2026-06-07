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
    data = [{"title": "Buy milk", "completed": False, "due": "2026-06-08", "notes": "", "priority": 0, "list": "Shopping"}]
    out = fmt.reminders(data)
    assert "Buy milk" in out
    assert "Shopping" in out
    assert "[ ]" in out


def test_reminders_completed():
    data = [{"title": "Done task", "completed": True, "due": None, "notes": "", "priority": 0, "list": "Inbox"}]
    out = fmt.reminders(data)
    assert "[x]" in out


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
    assert fmt.emails([]) == "No emails."


def test_emails():
    data = [{"message_id": "<abc@x>", "from": "bob@example.com", "to": "me@x.com", "subject": "Hello there", "date": "Sun, 07 Jun 2026 10:00:00"}]
    out = fmt.emails(data)
    assert "bob@example.com" in out
    assert "Hello there" in out


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


# --- tasks ---

def test_tasks_empty():
    assert fmt.tasks([]) == "No tasks."


def test_tasks():
    data = [{"id": 42, "title": "Write tests", "done": False, "due_date": "2026-06-10T00:00:00Z", "priority": 2, "project_id": 1, "description": "", "labels": [], "reminders": [], "related_tasks": {}}]
    out = fmt.tasks(data)
    assert "#42" in out
    assert "Write tests" in out
    assert "2026-06-10" in out


def test_tasks_done():
    data = [{"id": 1, "title": "Done thing", "done": True, "due_date": None, "priority": 0, "project_id": 1, "description": "", "labels": [], "reminders": [], "related_tasks": {}}]
    out = fmt.tasks(data)
    assert "[x]" in out


# --- projects ---

def test_projects_empty():
    assert fmt.projects([]) == "No projects."


def test_projects():
    data = [{"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": None}]
    out = fmt.projects(data)
    assert "#1" in out
    assert "Inbox" in out


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
