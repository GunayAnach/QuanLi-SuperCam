"""export_session.py - dump opencode session history to Markdown (full depth).

Reads the local opencode SQLite store (read-only) and writes one Markdown file
per session: user/assistant text verbatim, assistant reasoning blocks, tool
calls (with result summaries), and compaction markers.

Usage:
  python export_session.py [--db PATH] [--out DIR] [--session SES_ID]
                            [--quiet] [--no-index]

Defaults:
  db : auto-detected (Windows: %USERPROFILE%\\.local\\share\\opencode\\opencode.db
       else ~/.local/share/opencode/opencode.db)
  out: <repo>/docs/session_logs  (relative to this script's project root)
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys

REDACT_PATTERNS = [
    re.compile(r'\b(sk-[A-Za-z0-9_-]{16,})\b'),
    re.compile(r'\b(gh[pousr]_[A-Za-z0-9_]{24,})\b'),
    re.compile(r'\b(api[_-]?key["\']?\s*[:=]\s*["\']?)([^\s"\']{8,})', re.I),
    re.compile(r'\b(xox[baprs]-[A-Za-z0-9-]{16,})\b'),
    re.compile(r'\b(eyJ[A-Za-z0-9_.-]{20,})\b'),
    re.compile(r'\b([A-Za-z0-9+/]{40,}={0,2})\b'),
]


def redact(text):
    for pat in REDACT_PATTERNS[:-1]:
        text = pat.sub(lambda m: m.group(1)[:6] + '[REDACTED]', text)
    text = REDACT_PATTERNS[-1].sub('[REDACTED]', text)
    return text


def ts(ms):
    if not ms:
        return ''
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime('%Y-%m-%d %H:%M:%S')


def slug(title):
    s = re.sub(r'[^\w\- ]+', '', (title or 'session')).strip().replace(' ', '-').lower()
    s = re.sub(r'-{2,}', '-', s)
    return (s or 'session')[:70]


def trunc(text, n=800):
    if text is None:
        return ''
    text = str(text)
    return text if len(text) <= n else text[:n] + ' ...<truncated>'


def load_data(cur, table, sid):
    cur.execute('SELECT data FROM %s WHERE session_id=? ORDER BY time_created, rowid' % table, (sid,))
    return [json.loads(r[0]) for r in cur.fetchall()]


def part_md(p, msg_role):
    t = p.get('type')
    if t == 'text':
        text = p.get('text') or ''
        return redact(text)
    if t == 'reasoning':
        body = redact(p.get('text') or '')
        return '\n<details><summary>thinking</summary>\n\n%s\n\n</details>\n' % body
    if t == 'tool':
        state = p.get('state') or {}
        status = state.get('status', '?')
        inp = state.get('input') or {}
        out = state.get('output') or ''
        if isinstance(inp, dict):
            args = ', '.join('%s=%s' % (k, trunc(v, 120)) for k, v in inp.items())
        else:
            args = trunc(inp, 200)
        if isinstance(out, str):
            out = trunc(out, 500)
        else:
            out = trunc(json.dumps(out, default=str), 500)
        return '\n```[tool:%s %s]\n%s\n```\n' % (p.get('tool', '?'), status, args) + (
            '\n> result: %s\n' % out if out else '')
    if t == 'compaction':
        return '\n> **compaction %s** auto=%s overflow=%s\n' % (
            (p.get('tail_start_id') or ''), p.get('auto'), p.get('overflow'))
    return ''  # step-start / step-finish handled by caller


def main():
    ap = argparse.ArgumentParser(description='Export opencode session transcripts to Markdown')
    ap.add_argument('--db', default=None, help='path to opencode.db')
    ap.add_argument('--out', default=None, help='output docs dir (default: repo docs/session_logs)')
    ap.add_argument('--session', default=None, help='only export this session id')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--no-index', action='store_true')
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(repo, 'docs', 'session_logs')
    os.makedirs(out_dir, exist_ok=True)

    db = args.db
    if not db:
        home = os.path.expanduser('~')
        for cand in (os.path.join(home, '.local', 'share', 'opencode', 'opencode.db'),
                     os.path.join(os.environ.get('APPDATA', ''), 'opencode', 'opencode.db'),
                     os.path.join(home, 'Library', 'Application Support', 'opencode', 'opencode.db')):
            if cand and os.path.isfile(cand):
                db = cand
                break
    if not db or not os.path.isfile(db):
        print('ERROR: opencode.db not found; pass --db', file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    cur = con.cursor()

    cur.execute("""SELECT id,title,directory,time_created,time_updated,parent_id,agent,model
                   FROM session ORDER BY time_created""")
    sessions = []
    for sid, title, directory, tc, tu, parent, agent, model in cur.fetchall():
        if args.session and sid != args.session:
            continue
        cur.execute('SELECT COUNT(*) FROM message WHERE session_id=?', (sid,))
        nmsg = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM part WHERE session_id=?', (sid,))
        npart = cur.fetchone()[0]
        sessions.append(dict(id=sid, title=title or sid, directory=directory, created=tc,
                             updated=tu, parent=parent, agent=agent, model=model,
                             nmsg=nmsg, npart=npart))

    if not sessions:
        print('no sessions selected', file=sys.stderr)
        sys.exit(1)

    files = []
    for i, s in enumerate(sessions, 1):
        sid = s['id']
        cur.execute("""SELECT id, data FROM message WHERE session_id=? ORDER BY time_created, rowid""", (sid,))
        msgs = [(mid, json.loads(d)) for mid, d in cur.fetchall()]
        cur.execute("""SELECT message_id, data FROM part WHERE session_id=? ORDER BY time_created, rowid""", (sid,))
        parts_by_msg = {}
        for mid, d in cur.fetchall():
            parts_by_msg.setdefault(mid, []).append(json.loads(d))

        mdl = s['model'] or ''
        body = []
        body.append('# Session: %s\n' % s['title'])
        body.append('')
        body.append('- session id: `%s`' % sid)
        body.append('- directory: `%s`' % (s['directory'] or ''))
        body.append('- created: %s' % ts(s['created']))
        body.append('- updated: %s' % ts(s['updated']))
        if s['parent']:
            body.append('- parent session: `%s`' % s['parent'])
        if s['agent']:
            body.append('- agent: `%s`' % s['agent'])
        if mdl:
            body.append('- model: `%s`' % mdl)
        body.append('- messages: %d | parts: %d' % (s['nmsg'], s['npart']))
        body.append('')

        for mid, m in msgs:
            role = m.get('role', '?')
            models = m.get('model') or m.get('modelID') or ''
            if isinstance(models, dict):
                models = models.get('id', '')
            body.append('## %s%s\n' % (role.upper(), ('  [%s]' % models) if isinstance(models, str) and models and models != mdl else ''))
            for p in parts_by_msg.get(mid, []):
                pt = p.get('type')
                if pt in ('step-start', 'step-finish'):
                    continue
                md = part_md(p, role)
                if md:
                    body.append(md)
                body.append('')
        fname = '%03d_%s_%s.md' % (i, datetime.datetime.fromtimestamp(s['created'] / 1000).strftime('%Y%m%d_%H%M%S'), slug(s['title']))
        fpath = os.path.join(out_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(body))
        files.append((fname, s))
        if not args.quiet:
            print('wrote %s (%d msgs)' % (fname, s['nmsg']))

    if not args.no_index:
        index = ['# Session Log Index', '']
        index.append('Regenerated with `python tools/export_session.py` (full depth: text + reasoning + tool calls + compaction markers).')
        index.append('')
        index.append('| # | file | title | agent | msgs | created | updated |')
        index.append('|---|------|-------|-------|------|---------|---------|')
        for fname, s in files:
            index.append('| %-3d | %s | %s | %s | %d | %s | %s |' % (
                int(fname[:3]), fname, (s['title'].replace('|', '\\|') or '')[:60],
                (s['agent'] or 'main')[:40], s['nmsg'], ts(s['created']), ts(s['updated'])))
        with open(os.path.join(out_dir, '0000_session-index.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(index) + '\n')
        if not args.quiet:
            print('wrote index')

    if not args.quiet:
        print('done -> %s' % out_dir)


if __name__ == '__main__':
    main()