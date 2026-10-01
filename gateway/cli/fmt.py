from __future__ import annotations


def calendar_events(events: list) -> str:
    if not events:
        return "No events."
    lines = []
    for ev in events:
        start = (ev.get("start") or "")[:16]
        title = ev.get("title", "")
        cal = ev.get("calendar", "")
        loc = ev.get("location", "")
        lines.append(f"{start}  {title}  [{cal}]")
        if loc:
            lines.append(f"{'':16}  {loc}")
    return "\n".join(lines)


def calendars(data: list) -> str:
    if not data:
        return "No calendars."
    return "\n".join(c["name"] for c in data)


def reminders(data: list) -> str:
    if not data:
        return "No reminders."
    lines = []
    for r in data:
        done = "x" if r.get("done") else " "
        due = f"  due:{r['due']}" if r.get("due") else ""
        lst = f"  [{r['list']}]" if r.get("list") else ""
        lines.append(f"[{done}] {r['title']}{due}{lst}")
        loc = r.get("location")
        if loc:
            name = loc.get("name") or f"{loc.get('lat')},{loc.get('lon')}"
            lines.append(f"      📍 {name} ({loc.get('trigger', 'arrive')}, {loc.get('radius_m', 150)}m)")
    return "\n".join(lines)


def reminder_lists(data: list) -> str:
    if not data:
        return "No reminder lists."
    return "\n".join(r["name"] for r in data)


def contacts(data: list) -> str:
    if not data:
        return "No contacts found."
    lines = []
    for c in data:
        lines.append(c.get("name") or "(no name)")
        if c.get("organisation"):
            lines.append(f"  {c['organisation']}")
        for e in c.get("emails", []):
            lines.append(f"  {e}")
        for p in c.get("phones", []):
            lines.append(f"  {p}")
        lines.append("")
    return "\n".join(lines).rstrip()


def emails(data: dict) -> str:
    messages = data.get("messages", [])
    if not messages:
        return "No emails."
    multi_account = len({m.get("account") for m in messages}) > 1
    lines = []
    for e in messages:
        frm = (e.get("from") or "")[:35]
        subj = (e.get("subject") or "")[:55]
        date = (e.get("date") or "")[:16]
        acct = f"[{e.get('account')}] " if multi_account else ""
        lines.append(f"{date}  {acct}{frm:<35}  {subj}")
    if data.get("next_cursor"):
        lines.append(f"\n(more: --cursor {data['next_cursor']})")
    return "\n".join(lines)


def email_body(data: dict) -> str:
    return "\n".join([
        f"From:    {data.get('from', '')}",
        f"To:      {data.get('to', '')}",
        f"Subject: {data.get('subject', '')}",
        f"Date:    {data.get('date', '')}",
        "",
        data.get("body") or data.get("body_preview", ""),
    ])


def notes(data: list) -> str:
    return "\n".join(data) if data else "No notes."


def note_content(data: dict) -> str:
    if "error" in data:
        return f"Error: {data['error']}"
    return f"# {data['path']}\n\n{data['content']}"


def note_search_results(data: list) -> str:
    if not data:
        return "No matches."
    lines = []
    for r in data:
        if r.get("match_type") == "content" and r.get("context"):
            lines.append(f"{r['path']}:{r.get('line', '?')}  {r['context']}")
        else:
            lines.append(r["path"])
    return "\n".join(lines)


def bookmarks(data: dict | list) -> str:
    items = data.get("bookmarks", data) if isinstance(data, dict) else data
    if not items:
        return "No bookmarks."
    lines = []
    for b in items:
        title = b.get("title") or b.get("url") or b.get("id")
        url = b.get("url") or ""
        tags = ", ".join(b.get("tags", []))
        lines.append(f"{b['id']}  {title}")
        if url and url != title:
            lines.append(f"       {url}")
        if tags:
            lines.append(f"       #{tags}")
    return "\n".join(lines)


def bookmark_detail(b: dict) -> str:
    lines = [f"{b['id']}  {b.get('title') or b.get('url') or ''}"]
    if b.get("url"):
        lines.append(f"  URL:  {b['url']}")
    if b.get("summary"):
        lines.append(f"  {b['summary']}")
    if b.get("tags"):
        lines.append(f"  Tags: {', '.join(b['tags'])}")
    if b.get("note"):
        lines.append(f"  Note: {b['note']}")
    return "\n".join(lines)


def tags(data: list) -> str:
    if not data:
        return "No tags."
    return "\n".join(f"{t['name']} ({t.get('count', 0)})" for t in data)


def lists(data: list) -> str:
    if not data:
        return "No lists."
    return "\n".join(f"{l['id']}  {l.get('icon', '')} {l['name']}" for l in data)


def issues(data: list) -> str:
    if not data:
        return "No issues."
    lines = []
    for t in data:
        mark = "x" if t.get("status") == "done" else " "
        due = f"  due:{t['due'][:10]}" if t.get("due") else ""
        pri = f"  p{t['priority']}" if t.get("priority") else ""
        proj = f"  [{t['project']}]" if t.get("project") else ""
        lines.append(f"[{mark}] #{t['id']}  {t['title']}{proj}{due}{pri}")
    return "\n".join(lines)


def issue_detail(t: dict) -> str:
    lines = [
        f"#{t['id']} {t['title']}",
        f"  Status:   {t.get('status', 'open')}",
        f"  Priority: {t.get('priority', 0)}",
        f"  Due:      {t.get('due') or '-'}",
        f"  Project:  {t.get('project') or '-'}",
    ]
    if t.get("description"):
        lines += ["", t["description"]]
    if t.get("labels"):
        lines.append(f"  Labels:   {', '.join(t['labels'])}")
    if t.get("related"):
        lines.append(f"  Related:  {', '.join('#' + str(i) for i in t['related'])}")
    if t.get("checklist"):
        lines.append("\nChecklist:")
        for item in t["checklist"]:
            mark = "x" if item.get("done") else " "
            lines.append(f"  [{mark}] {item['text']}")
    if t.get("comments"):
        lines.append("\nComments:")
        for c in t["comments"]:
            lines.append(f"  {c['timestamp']}: {c['text']}")
    return "\n".join(lines)


def comments(data: list) -> str:
    if not data:
        return "No comments."
    lines = []
    for c in data:
        lines.append(f"#{c['id']} by {c.get('author', '')} on {(c.get('created') or '')[:10]}")
        lines.append(f"  {c['comment']}")
    return "\n".join(lines)


def location(data: dict) -> str:
    if "error" in data:
        return f"Error: {data['error']}"
    parts = [f"Lat: {data.get('lat')}, Lon: {data.get('lon')}"]
    if data.get("address"):
        parts.append(f"Address: {data['address']}")
    if data.get("timestamp"):
        parts.append(f"Updated: {data['timestamp']}")
    if data.get("accuracy_m"):
        parts.append(f"Accuracy: {data['accuracy_m']}m")
    return "\n".join(parts)


def location_history(data: dict) -> str:
    points = data.get("points", [])
    if not points:
        return "No location history."
    lines = [f"Count: {data.get('count', len(points))}"]
    for p in points[-20:]:
        ts = (p.get("timestamp") or "")[:16]
        addr = p.get("address") or f"{p.get('lat')},{p.get('lon')}"
        lines.append(f"  {ts}  {addr}")
    return "\n".join(lines)


def devices(data: list) -> str:
    if not data:
        return "No devices."
    lines = []
    for d in data:
        devs = ", ".join(d.get("devices", []))
        lines.append(f"{d['user']}: {devs}" if devs else d["user"])
    return "\n".join(lines)
