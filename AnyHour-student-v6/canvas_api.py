"""Read-only Canvas OAuth integration for a local demo.

Tokens are stored only in server memory, keyed by an HttpOnly browser session cookie.
Institution-approved Developer Key is required for a real connection.
"""
import json, os, secrets, threading, time, urllib.parse, urllib.request, urllib.error
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

BASE=os.getenv('CANVAS_BASE_URL','').rstrip('/')
CLIENT_ID=os.getenv('CANVAS_CLIENT_ID','')
CLIENT_SECRET=os.getenv('CANVAS_CLIENT_SECRET','')
REDIRECT=os.getenv('CANVAS_REDIRECT_URI','http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/canvas/callback')
ENABLED=bool(BASE and CLIENT_ID and CLIENT_SECRET and BASE.startswith('https://') and not urlsplit(BASE).username and not urlsplit(BASE).query and urlsplit(BASE).path in ('','/'))
_lock=threading.RLock()
_sessions={}

def _new_id():return secrets.token_urlsafe(32)
def session(handler):
    cookie=SimpleCookie()
    try:cookie.load(handler.headers.get('Cookie',''))
    except Exception:pass
    sid=cookie.get('cp_canvas_session')
    sid=sid.value if sid else None
    with _lock:
        if sid and sid in _sessions:return sid,_sessions[sid],False
        sid=_new_id();_sessions[sid]={'oauth_state':None,'access_token':None,'refresh_token':None,'expires':0,'user':None}
        return sid,_sessions[sid],True

def session_cookie(sid):return f'cp_canvas_session={sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400'

def config_status(data):
    return {'configured':ENABLED,'connected':bool(data.get('access_token')),'canvas_domain':urlsplit(BASE).hostname if ENABLED else None,'user':data.get('user')}

def connect(handler):
    sid,data,created=session(handler)
    if not ENABLED:raise ValueError('Canvas OAuth is not configured. Set CANVAS_BASE_URL, CANVAS_CLIENT_ID, and CANVAS_CLIENT_SECRET.')
    nonce=_new_id()
    with _lock:data['oauth_state']=(nonce,time.time()+600)
    scope=os.getenv('CANVAS_SCOPES','').strip()
    params={'client_id':CLIENT_ID,'response_type':'code','redirect_uri':REDIRECT,'state':nonce}
    if scope:params['scope']=scope
    return sid,BASE+'/login/oauth2/auth?'+urllib.parse.urlencode(params)

def post_token(params):
    req=urllib.request.Request(BASE+'/login/oauth2/token',data=urllib.parse.urlencode(params).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    with urllib.request.urlopen(req,timeout=20) as res:return json.load(res)

def callback(handler,params):
    sid,data,created=session(handler)
    state=params.get('state',[''])[0]
    with _lock:
        pending=data.get('oauth_state');data['oauth_state']=None
    if not pending or not secrets.compare_digest(state,pending[0]) or time.time()>pending[1]:raise ValueError('Canvas authorization expired or did not match this browser session')
    if params.get('error'):raise ValueError('Canvas denied access: '+params['error'][0][:100])
    code=params.get('code',[''])[0]
    if not code:raise ValueError('Canvas did not return an authorization code')
    tokens=post_token({'grant_type':'authorization_code','client_id':CLIENT_ID,'client_secret':CLIENT_SECRET,'redirect_uri':REDIRECT,'code':code})
    with _lock:
        data.update(access_token=tokens['access_token'],refresh_token=tokens.get('refresh_token'),expires=time.time()+int(tokens.get('expires_in',3600))-60,user=tokens.get('user',{}).get('name') if isinstance(tokens.get('user'),dict) else None)
    return sid

def access(data):
    with _lock:
        if not data.get('access_token'):raise ValueError('Connect Canvas first')
        if time.time()<data['expires']:return data['access_token']
        refresh=data.get('refresh_token')
    if not refresh:raise ValueError('Canvas session expired. Reconnect.')
    tokens=post_token({'grant_type':'refresh_token','client_id':CLIENT_ID,'client_secret':CLIENT_SECRET,'refresh_token':refresh})
    with _lock:
        data.update(access_token=tokens['access_token'],refresh_token=tokens.get('refresh_token',refresh),expires=time.time()+int(tokens.get('expires_in',3600))-60)
        return data['access_token']

def fetch_paginated(data,endpoint,query=None):
    # All requests and pagination links must stay on the configured Canvas hostname.
    token=access(data)
    url=BASE+endpoint+('?' + urllib.parse.urlencode(query) if query else '')
    results=[]
    for _ in range(12):
        parsed=urlsplit(url)
        root=urlsplit(BASE)
        if parsed.scheme!='https' or parsed.netloc!=root.netloc or not parsed.path.startswith('/api/v1/'):
            raise ValueError('Unexpected Canvas pagination URL')
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/json+canvas-string-ids'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                page=json.load(response)
                link=response.headers.get('Link','')
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise ValueError('Canvas refused access; reconnect or ask your institution to allow the required read scopes')
            raise ValueError('Canvas request failed (HTTP '+str(exc.code)+')')
        if not isinstance(page,list):raise ValueError('Unexpected Canvas response')
        results.extend(page)
        if len(results)>=500:break
        import re
        nextlink=re.search(r'<([^>]+)>\s*;\s*rel="next"',link)
        if not nextlink:break
        url=nextlink.group(1)
    return results[:500]

def courses(data):
    items=fetch_paginated(data,'/api/v1/courses',{'enrollment_state':'active','per_page':100})
    return [{'id':str(c['id']),'name':c.get('name') or 'Untitled Canvas course','code':c.get('course_code') or '', 'url':BASE+'/courses/'+str(c['id'])} for c in items if c.get('id') is not None and c.get('workflow_state')!='deleted']

def assignments(data,course_id):
    if not str(course_id).isdigit():raise ValueError('Invalid Canvas course ID')
    # Only allow courses that this authorized Canvas account can list.
    allowed={x['id'] for x in courses(data)}
    if str(course_id) not in allowed:raise ValueError('The selected Canvas course is not available to your account')
    rows=fetch_paginated(data,'/api/v1/courses/'+str(course_id)+'/assignments',{'per_page':100,'order_by':'due_at'})
    result=[]
    for x in rows:
        if x.get('id') is None or x.get('published') is False:continue
        link=x.get('html_url') or BASE+'/courses/'+str(course_id)+'/assignments/'+str(x['id'])
        if urlsplit(link).scheme!='https' or urlsplit(link).netloc!=urlsplit(BASE).netloc:link=BASE+'/courses/'+str(course_id)+'/assignments/'+str(x['id'])
        result.append({'id':str(x['id']),'name':x.get('name','Assignment'),'due_at':x.get('due_at'),'unlock_at':x.get('unlock_at'),'points_possible':x.get('points_possible'),'url':link,'course_id':str(course_id)})
    return result

def disconnect(data):
    with _lock:data.update(access_token=None,refresh_token=None,expires=0,user=None,oauth_state=None)
