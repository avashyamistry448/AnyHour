"""ClassPilot professor-first demo. Launch: python3 server.py"""
import base64, hashlib, hmac, io, json, mimetypes, os, re, secrets, sqlite3, urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from course_ai import grading_answer, rank_syllabus_pages, local_answer, ollama_available

ROOT=Path(__file__).resolve().parent
DB=ROOT/'classpilot.db'
MAX_SIZE=32_000_000

def db():
    conn=sqlite3.connect(DB,timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def utcnow():return datetime.now(timezone.utc).isoformat()
def seed():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, term TEXT NOT NULL DEFAULT 'Fall 2026', color TEXT NOT NULL DEFAULT '#5a72e8');
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS faq(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, question TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS join_codes(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, digest TEXT UNIQUE NOT NULL, hint TEXT NOT NULL, expires_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS enrollments(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, student_name TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(course_id,student_name));
        CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, event TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK (id=1), full_name TEXT NOT NULL, department TEXT NOT NULL, institution TEXT NOT NULL, email TEXT NOT NULL, bio TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS syllabi(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL UNIQUE REFERENCES courses(id) ON DELETE CASCADE, filename TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', pages_json TEXT NOT NULL, imported_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS office_hours(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE, weekday INTEGER NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL, meeting_type TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', booking_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS canvas_links(course_id INTEGER PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE, url TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS office_settings(course_id INTEGER PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE, mode TEXT NOT NULL DEFAULT 'syllabus', instructions TEXT NOT NULL DEFAULT '', booking_url TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        ''')
        columns=[r['name'] for r in c.execute('PRAGMA table_info(courses)')]
        if 'section' not in columns:c.execute("ALTER TABLE courses ADD COLUMN section TEXT NOT NULL DEFAULT '001'")
        if 'course_code' not in columns:c.execute("ALTER TABLE courses ADD COLUMN course_code TEXT NOT NULL DEFAULT ''")
        c.execute("UPDATE courses SET course_code=code WHERE course_code=''")
        c.execute('INSERT OR IGNORE INTO profile VALUES(1,?,?,?,?,?)',('Dr. Avery Morgan','Department of Engineering','Northfield University','amorgan@northfield.example','I help students build strong foundations through practical projects and thoughtful questions.'))
        if c.execute('SELECT COUNT(*) FROM courses').fetchone()[0]==0:
            for code,name,color in [('ENGR 102','Engineering Design Studio','#5674ed'),('MATH 152','Engineering Mathematics II','#9b71db'),('PHYS 206','University Physics I','#17a889')]:
                c.execute('INSERT INTO courses(code,course_code,section,name,term,color) VALUES(?,?,?,?,?,?)',(code,code,'001',name,'Fall 2026',color))
            cid=c.execute("SELECT id FROM courses WHERE code='ENGR 102'").fetchone()['id']
            for kind,title,body,url in [

                ('contact','Instructor contact','Email: amorgan@northfield.example. Include ENGR 102 in the subject line. Typical response time: two business days.',''),
                ('resource','Python practice exercises','Optional practice problems for Python fundamentals.','https://docs.python.org/3/tutorial/'),
                ('notes','Python lab tips','Supplemental tips for practicing Python. Official assignments and submission requirements are maintained in Canvas.','')]:
                c.execute('INSERT INTO materials(course_id,kind,title,body,url,created_at) VALUES(?,?,?,?,?,?)',(cid,kind,title,body,url,utcnow()))
            for q,a in [('Can I submit assignments late?','Please contact the instructor before the deadline for any extension request. Refer to the current assignment instructions for policies.'),('Where can I get help with Python?','Attend Tuesday office hours or use the Python practice resource in the course materials.'),('Are teams required for projects?','Project instructions specify whether a submission is individual or team-based.')]:
                c.execute('INSERT INTO faq(course_id,question,answer,created_at) VALUES(?,?,?,?)',(cid,q,a,utcnow()))
            for e,n in [('material_view','Course overview'),('faq_view','Can I submit assignments late?'),('assistant_question','When is my project due?'),('assistant_question','Where are office hours?'),('material_view','Project 1 brief')]:
                c.execute('INSERT INTO activity(course_id,event,subject,created_at) VALUES(?,?,?,?)',(cid,e,n,utcnow()))
            # FINP 235 section 598 is an example extracted directly from the user-provided
            # 14-page printed Simple Syllabus PDF. It remains a demo reference section.
            sample=ROOT/'sample_finp235_pages.json'
            if sample.exists():
                c.execute('INSERT INTO courses(code,course_code,section,name,term,color) VALUES(?,?,?,?,?,?)',('FINP 235 | 598 | Fall 2026','FINP 235','598','Foundations of Money Education','Fall 2026','#487da0'))
                finp_id=c.execute("SELECT id FROM courses WHERE course_code='FINP 235' AND section='598'").fetchone()['id']
                c.execute('INSERT INTO syllabi(course_id,filename,source_url,pages_json,imported_at) VALUES(?,?,?,?,?)',(finp_id,'FINP 235 598 - Simple Syllabus.pdf','https://tamu.simplesyllabus.com/en-US/doc/yo3mszqo5',sample.read_text(encoding='utf-8'),utcnow()))


def digest(code):return hashlib.sha256(code.strip().upper().encode()).hexdigest()
def read_json(handler):
    n=int(handler.headers.get('Content-Length','0'))
    if n<1 or n>MAX_SIZE*2:raise ValueError('Request is empty or too large')
    return json.loads(handler.rfile.read(n))
def exists(c,cid):return c.execute('SELECT id FROM courses WHERE id=?',(cid,)).fetchone() is not None
def syllabi_for_course(c,cid):
    rec=c.execute('SELECT * FROM syllabi WHERE course_id=?',(cid,)).fetchone()
    return dict(rec) if rec else None

def extract_syllabus_details(pages):
    text='\n'.join(pages[:8])
    def one(pattern):
        m=re.search(pattern,text,re.I)
        return re.sub(r'\s+',' ',m.group(1)).strip() if m else ''
    return {'instructor':one(r'Instructor Details\s*([^\n]+)'),
            'email':one(r'Email:\s*([^\n]+)'),
            'office':one(r'Office Location:\s*([^\n]+)'),
            'office_hours':one(r'Office Hours\s*([^\n]+)'),
            'course_dates':one(r'Start Date:\s*([^\n]+)'),
            'grading':one(r'Grading Policy\s*([^\n]{5,120})'),
            'grading_weights':[re.sub(r'\s+',' ',line).strip() for line in pages[4].splitlines() if re.search(r'(Quizzes|Assignments|Exams|Reflection Video|Extra Credit):\s*\d+%',line,re.I)][:6] if len(pages)>4 else []}

def syllabus_matches(pages, question):
    return rank_syllabus_pages(pages, question)

def search_answer(c,cid,question):
    q=question.casefold()
    rows=c.execute('SELECT question,answer FROM faq WHERE course_id=?',(cid,)).fetchall()
    stop={'what','when','where','will','with','from','this','that','about','have','does','your','need','the','for','can','are','and','how','do','is','to','my','in','a','i'}
    tokens=set(re.findall(r'[a-z0-9]{3,}',q))-stop
    def score(t):
        txt=t.casefold();return len(tokens.intersection(re.findall(r'[a-z0-9]{3,}',txt)))
    official=syllabi_for_course(c,cid)
    official_pages=json.loads(official['pages_json']) if official else []
    verified=grading_answer(official_pages, question) if official else None
    if verified:
        return verified
    official_results=syllabus_matches(official_pages, question) if official else []
    policy_terms=('syllabus','grading','grade','late','deadline','due','quiz','exam','policy','office','email','instructor','schedule','credit','attendance')
    official_question=any(w in q for w in policy_terms)
    candidates=[]
    for row in rows:
        rating=score(row['question'])*3+score(row['answer'])
        if rating>0:candidates.append((rating,{'title':'FAQ: '+row['question'],'answer':row['answer'],'kind':'faq'}))
    for row in c.execute("SELECT title,body,kind FROM materials WHERE course_id=? AND kind IN ('contact','resource','notes','document')",(cid,)):
        rating=score(row['title'])*3+score(row['body'])
        if rating>0:candidates.append((rating,{'title':row['title'],'answer':row['body'][:2200],'kind':row['kind']}))
    candidates.sort(key=lambda item:-item[0]);matches=[item for _,item in candidates[:3]]
    if official_results and official_question:
        matches=[v for _,v in official_results[:3]]
        # Official document overrides conflicting informal FAQs for course policies.
    elif not matches and official_results:
        matches=[v for _,v in official_results[:3]]
    if not matches and any(k in q for k in ('office hour','meeting time','appointment')):
        times=c.execute('SELECT * FROM office_hours WHERE course_id=? ORDER BY weekday,start_time',(cid,)).fetchall()
        if times:
            days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            answer='\n'.join(f"{days[t['weekday']]} {t['start_time']}–{t['end_time']} ({t['meeting_type']}) {t['location']}" for t in times)
            return {'answer':answer,'sources':['Office hours calendar'],'mode':'calendar'}
    if not matches:return {'answer':'I could not find a verified answer in this section’s materials or FAQs. Please check with your professor.','sources':[],'mode':'no_match'}
    if matches[0]['kind']=='faq':return {'answer':matches[0]['answer'],'sources':[matches[0]['title']],'mode':'faq'}
    return local_answer(question, matches)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def reply(self,data,status=200):
        b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def error(self,exc,status=400):self.reply({'error':str(exc)},status)
    def do_GET(self):
        path=urlsplit(self.path).path
        if not path.startswith('/api/'):return super().do_GET()
        try:
            with db() as c:
                if path=='/api/state':
                    courses=[dict(r) for r in c.execute('SELECT * FROM courses ORDER BY code')]
                    materials=[dict(r) for r in c.execute('SELECT * FROM materials ORDER BY id DESC')]
                    faqs=[dict(r) for r in c.execute('SELECT * FROM faq ORDER BY id DESC')]
                    codes=[dict(r) for r in c.execute('SELECT id,course_id,hint,expires_at,active,created_at FROM join_codes ORDER BY id DESC')]
                    enrollments=[dict(r) for r in c.execute('SELECT * FROM enrollments ORDER BY id DESC')]
                    activity=[dict(r) for r in c.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 200')]
                    profile=dict(c.execute('SELECT * FROM profile WHERE id=1').fetchone())
                    syllabi=[{'id':r['id'],'course_id':r['course_id'],'filename':r['filename'],'source_url':r['source_url'],'page_count':len(json.loads(r['pages_json'])),'imported_at':r['imported_at'],'details':extract_syllabus_details(json.loads(r['pages_json']))} for r in c.execute('SELECT * FROM syllabi')]
                    office_hours=[dict(r) for r in c.execute('SELECT * FROM office_hours ORDER BY weekday,start_time')]
                    office_settings=[dict(r) for r in c.execute('SELECT * FROM office_settings')]
                    canvas_links=[dict(r) for r in c.execute('SELECT * FROM canvas_links')]
                    return self.reply({'courses':courses,'materials':materials,'faqs':faqs,'codes':codes,'enrollments':enrollments,'activity':activity,'profile':profile,'syllabi':syllabi,'office_hours':office_hours,'office_settings':office_settings,'canvas_links':canvas_links,'ai_enabled':ollama_available()})
                if path=='/api/health':return self.reply({'status':'ok'})
            self.error('Not found',404)
        except Exception as ex:self.error(ex,500)
    def do_POST(self):
        path=urlsplit(self.path).path
        try:
            data=read_json(self)
            with db() as c:
                if path=='/api/course':
                    base=str(data.get('code','')).upper().strip();section=str(data.get('section','001')).upper().strip();name=str(data.get('name','')).strip();term=str(data.get('term','Fall 2026')).strip()
                    if not re.fullmatch(r'[A-Z0-9][A-Z0-9 -]{1,29}',base) or not re.fullmatch(r'[A-Z0-9-]{1,15}',section) or not 1<=len(name)<=100 or len(term)>60:raise ValueError('Enter a valid course code, section, name, and term')
                    code=base+' | '+section+' | '+term
                    cur=c.execute('INSERT INTO courses(code,course_code,section,name,term) VALUES(?,?,?,?,?)',(code,base,section,name,term));return self.reply({'id':cur.lastrowid})
                if path=='/api/material':
                    cid=int(data['course_id']);kind=str(data.get('kind','notes'));title=str(data.get('title','')).strip();body=str(data.get('body','')).strip();url=str(data.get('url','')).strip()
                    if not exists(c,cid):raise ValueError('Unknown course')
                    if kind not in {'contact','resource','document','notes'}:raise ValueError('Unknown category')
                    if not (1<=len(title)<=140) or len(body)>400000:raise ValueError('Title or content length is invalid')
                    if url and not re.match(r'^https?://',url):raise ValueError('Resource links must start with https:// or http://')
                    if not body and not url:raise ValueError('Enter text or a resource URL')
                    cur=c.execute('INSERT INTO materials(course_id,kind,title,body,url,created_at) VALUES(?,?,?,?,?,?)',(cid,kind,title,body,url,utcnow()))
                    return self.reply({'id':cur.lastrowid})
                if path=='/api/syllabus':
                    cid=int(data['course_id']);name=str(data.get('name','')).strip();url=str(data.get('url','')).strip()
                    if not exists(c,cid):raise ValueError('Unknown section')
                    if not name.lower().endswith('.pdf'):raise ValueError('Upload a PDF syllabus')
                    if url and not re.match(r'^https?://',url):raise ValueError('Enter a valid Simple Syllabus URL')
                    raw=base64.b64decode(data.get('base64',''),validate=True)
                    if len(raw)>MAX_SIZE:raise ValueError('PDF exceeds 32 MB')
                    try:from pypdf import PdfReader
                    except ImportError:raise ValueError('Install PDF support: python3 -m pip install -r requirements.txt')
                    pdf=PdfReader(io.BytesIO(raw))
                    if not 1<=len(pdf.pages)<=160:raise ValueError('PDF page count is invalid')
                    pages=[(p.extract_text() or '').strip() for p in pdf.pages]
                    txt='\n'.join(pages)
                    if not re.search(r'course information|grading policy|course learning outcomes|course syllabus|syllabus',txt,re.I):
                        raise ValueError('This PDF does not appear to contain a course syllabus')
                    if len(txt.strip())<200:raise ValueError('No selectable text found in the printed syllabus')
                    c.execute('INSERT INTO syllabi(course_id,filename,source_url,pages_json,imported_at) VALUES(?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET filename=excluded.filename,source_url=excluded.source_url,pages_json=excluded.pages_json,imported_at=excluded.imported_at',(cid,name,url,json.dumps(pages),utcnow()))
                    c.execute("DELETE FROM materials WHERE course_id=? AND kind='syllabus'",(cid,))
                    return self.reply({'ok':True,'page_count':len(pages),'details':extract_syllabus_details(pages)})
                if path=='/api/office_settings':
                    cid=int(data.get('course_id',0));mode=str(data.get('mode','syllabus'));instructions=str(data.get('instructions','')).strip();booking=str(data.get('booking_url','')).strip()
                    if not exists(c,cid) or mode not in ('syllabus','appointment','weekly') or len(instructions)>1500:raise ValueError('Enter valid office hour preferences')
                    if booking and (not booking.startswith(('https://','http://')) or len(booking)>500):raise ValueError('Enter a valid booking link')
                    c.execute('INSERT INTO office_settings(course_id,mode,instructions,booking_url,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(course_id) DO UPDATE SET mode=excluded.mode,instructions=excluded.instructions,booking_url=excluded.booking_url,updated_at=excluded.updated_at',(cid,mode,instructions,booking,utcnow()))
                    return self.reply({'ok':True})
                if path=='/api/office_hours':
                    cid=int(data.get('course_id',0));day=int(data.get('weekday',-1));start=str(data.get('start_time',''));end=str(data.get('end_time',''));meeting=str(data.get('meeting_type','In person'));location=str(data.get('location','')).strip();booking=str(data.get('booking_url','')).strip()
                    if not exists(c,cid) or not 0<=day<=6 or not re.fullmatch(r'\d{2}:\d{2}',start) or not re.fullmatch(r'\d{2}:\d{2}',end) or start>=end or meeting not in ('In person','Virtual','Hybrid','By appointment') or len(location)>200:raise ValueError('Enter a valid weekly office-hours schedule')
                    if booking and not booking.startswith(('https://','http://')):raise ValueError('Booking link must start with https://')
                    if c.execute('SELECT 1 FROM office_hours WHERE course_id=? AND weekday=? AND start_time<? AND end_time>?',(cid,day,end,start)).fetchone():raise ValueError('This time overlaps another office-hours slot on that day')
                    cur=c.execute('INSERT INTO office_hours(course_id,weekday,start_time,end_time,meeting_type,location,booking_url,created_at) VALUES(?,?,?,?,?,?,?,?)',(cid,day,start,end,meeting,location,booking,utcnow()))
                    return self.reply({'id':cur.lastrowid})
                if path=='/api/canvas_link':
                    cid=int(data['course_id']);url=str(data.get('url','')).strip()
                    if not exists(c,cid):raise ValueError('Unknown section')
                    if url and (not re.match(r'^https://[^/]+/',url) or len(url)>500):raise ValueError('Use a valid https:// Canvas course link')
                    c.execute('INSERT INTO canvas_links(course_id,url,updated_at) VALUES(?,?,?) ON CONFLICT(course_id) DO UPDATE SET url=excluded.url,updated_at=excluded.updated_at',(cid,url,utcnow()))
                    return self.reply({'ok':True})
                if path=='/api/upload':
                    cid=int(data['course_id']);name=str(data.get('name','')).strip();encoded=data.get('base64','')
                    if not exists(c,cid):raise ValueError('Unknown course')
                    if not name or len(name)>180:raise ValueError('Invalid filename')
                    raw=base64.b64decode(encoded,validate=True)
                    if len(raw)>MAX_SIZE:raise ValueError('Maximum file size is 32 MB')
                    ext=Path(name).suffix.lower()
                    if ext=='.pdf':
                        try:from pypdf import PdfReader
                        except ImportError:raise ValueError('Install PDF support: python3 -m pip install pypdf')
                        reader=PdfReader(io.BytesIO(raw))
                        if len(reader.pages)>120:raise ValueError('PDF is too long for this demo')
                        body='\n'.join((p.extract_text() or '') for p in reader.pages)
                    elif ext in {'.txt','.md'}:body=raw.decode('utf-8-sig')
                    else:raise ValueError('Only PDF, TXT, and MD documents are supported')
                    if not body.strip():raise ValueError('No selectable text found in the document')
                    cur=c.execute('INSERT INTO materials(course_id,kind,title,body,url,created_at) VALUES(?,?,?,?,?,?)',(cid,'document',name,body[:400000],'',utcnow()))
                    return self.reply({'id':cur.lastrowid})
                if path=='/api/faq':
                    cid=int(data['course_id']);q=str(data.get('question','')).strip();a=str(data.get('answer','')).strip()
                    if not exists(c,cid) or not (3<=len(q)<=300) or not (1<=len(a)<=5000):raise ValueError('Enter a valid question and answer')
                    cur=c.execute('INSERT INTO faq(course_id,question,answer,created_at) VALUES(?,?,?,?)',(cid,q,a,utcnow()));return self.reply({'id':cur.lastrowid})
                if path=='/api/code':
                    cid=int(data['course_id']);days=int(data.get('days',7))
                    if not exists(c,cid) or not 1<=days<=90:raise ValueError('Select a valid course and code duration')
                    code='CP-'+''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
                    exp=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
                    c.execute('INSERT INTO join_codes(course_id,digest,hint,expires_at,active,created_at) VALUES(?,?,?,?,1,?)',(cid,digest(code),code[-4:],exp,utcnow()))
                    return self.reply({'code':code,'expires_at':exp})
                if path=='/api/join':
                    code=str(data.get('code','')).strip().upper();student=str(data.get('student_name','')).strip()
                    if not 2<=len(student)<=100:raise ValueError('Enter a student display name')
                    rows=c.execute('SELECT * FROM join_codes WHERE active=1').fetchall()
                    match=next((r for r in rows if hmac.compare_digest(r['digest'],digest(code))),None)
                    if not match or match['expires_at']<=utcnow():raise ValueError('Invalid, expired, or revoked class code')
                    c.execute('INSERT OR IGNORE INTO enrollments(course_id,student_name,created_at) VALUES(?,?,?)',(match['course_id'],student,utcnow()))
                    name=c.execute('SELECT name FROM courses WHERE id=?',(match['course_id'],)).fetchone()['name']
                    return self.reply({'course_id':match['course_id'],'name':name})
                if path=='/api/profile':
                    fields=[str(data.get(k,'')).strip() for k in ('full_name','department','institution','email','bio')]
                    if not fields[0] or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',fields[3]) or any(len(f)>1200 for f in fields):raise ValueError('Enter a name and valid email')
                    c.execute('UPDATE profile SET full_name=?,department=?,institution=?,email=?,bio=? WHERE id=1',fields);return self.reply({'ok':True})
                if path=='/api/ask':
                    cid=int(data.get('course_id',0));q=str(data.get('question','')).strip()[:1200]
                    if not exists(c,cid) or not q:raise ValueError('Pick a class and ask a question')
                    result=search_answer(c,cid,q)
                    c.execute('INSERT INTO activity(course_id,event,subject,created_at) VALUES(?,?,?,?)',(cid,'assistant_question',q,utcnow()))
                    return self.reply(result)
                if path=='/api/activity':
                    cid=int(data.get('course_id',0));event=str(data.get('event',''))
                    if not exists(c,cid) or event not in {'material_view','faq_view'}:raise ValueError('Invalid activity event')
                    c.execute('INSERT INTO activity(course_id,event,subject,created_at) VALUES(?,?,?,?)',(cid,event,str(data.get('subject',''))[:200],utcnow()))
                    return self.reply({'ok':True})
                if path=='/api/revoke':
                    c.execute('UPDATE join_codes SET active=0 WHERE id=?',(int(data['id']),));return self.reply({'ok':True})
                if path=='/api/delete':
                    kind=str(data.get('kind'));table={'faq':'faq','material':'materials','course':'courses','office_hours':'office_hours'}.get(kind)
                    if not table:raise ValueError('Unsupported item')
                    c.execute('DELETE FROM '+table+' WHERE id=?',(int(data['id']),));return self.reply({'ok':True})
            self.error('Not found',404)
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError, json.JSONDecodeError) as ex:self.error(ex)
        except Exception as ex:self.error('Server error: '+str(ex),500)

if __name__=='__main__':
    seed()
    port=int(os.getenv('PORT',8000));print(f'ClassPilot running at http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
