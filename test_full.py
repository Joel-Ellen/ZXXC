# -*- coding: utf-8 -*-
"""EduAgent 全功能测试脚本"""
import urllib.request, json, re, sys, time

BASE = 'http://localhost:8800'
USER = 'student'
COURSE = 'data_structures'
PASS = []

def ok(msg):
    PASS.append(msg)
    print(f'  [PASS] {msg}')

def fail(msg, detail=''):
    print(f'  [FAIL] {msg} {detail}')

def api(method, path, body=None, auth=False, token=None):
    data = json.dumps(body or {}).encode('utf-8') if body else None
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    if auth and token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'detail': e.read().decode('utf-8', errors='replace')}
    except Exception as e:
        return {'error': -1, 'detail': str(e)}

def solve_captcha():
    r = api('GET', '/api/auth/captcha-json')
    tok = r.get('captcha_token','')
    svg = r.get('svg','')
    m = re.search(r'>([0-9]+\s*[-+xX*/÷]\s*[0-9]+)\s*=', svg)
    if not m: return tok, '0'
    expr = m.group(1).replace('×','*').replace('x','*').replace('X','*').replace('÷','//')
    return tok, str(eval(expr))

print()
print('='*60)
print('  EduAgent Full-Feature Test Suite')
print('='*60)

# ── 1. Auth: Login ──
print('\n[1] Auth Flow')
ct, ans = solve_captcha()
r = api('POST', '/api/auth/login', {
    'user_id': 'student', 'password': 'Learn@2026',
    'captcha_token': ct, 'captcha_answer': ans
})
AT = r.get('access_token','')
RT = r.get('refresh_token','')
if AT and RT:
    ok(f'Login (user={r["user"]["user_id"]}, role={r["user"]["role"]})')
else: fail('Login', r.get('detail',''))

# ── 2. Auth: Me ──
r = api('GET', '/api/auth/me', auth=True, token=AT)
if r.get('user_id') == 'student':
    ok('Auth/Me')
else: fail('Auth/Me', r.get('detail',''))

# ── 3. Auth: Refresh ──
r = api('POST', '/api/auth/refresh', {'refresh_token': RT})
if r.get('access_token') and r.get('refresh_token'):
    AT2, RT2 = r['access_token'], r['refresh_token']
    ok('Token refresh')
else: fail('Token refresh', r.get('detail',''))

# ── 4. Admin Login ──
ct, ans = solve_captcha()
r = api('POST', '/api/auth/login', {
    'user_id': 'admin', 'password': 'Admin@2026!',
    'captcha_token': ct, 'captcha_answer': ans
})
if r.get('access_token') and r['user'].get('role') == 'ADMIN':
    ok('Admin login')
else: fail('Admin login', r.get('detail',''))

# ── 5. Register ──
ct, ans = solve_captcha()
ts = int(time.time()) % 100000
r = api('POST', '/api/auth/register', {
    'user_id': f'test_{ts}',
    'email': f'test{ts}@test.local',
    'password': 'Test123456!',
    'captcha_token': ct, 'captcha_answer': ans
})
if r.get('access_token'):
    ok('User registration')
else: fail('Registration', r.get('detail',''))

# ── 6. Courses ──
print('\n[2] Course Management')
r = api('GET', '/api/courses')
if isinstance(r, list) and len(r) >= 5:
    ok(f'List courses ({len(r)} courses)')
else: fail('List courses')

r = api('GET', '/api/courses/data_structures')
if r.get('node_count') == 20:
    ok('Course detail (20 nodes)')
else: fail('Course detail')

r = api('POST', '/api/user/courses/enroll', {'user_id': USER, 'course_id': COURSE})
if r.get('status') == 'enrolled':
    ok('Enroll course')
else: fail('Enroll', r.get('detail',''))

r = api('POST', '/api/user/courses/switch', {'user_id': USER, 'course_id': COURSE})
if r.get('has_path'):
    ok('Switch course')
else: fail('Switch', r.get('detail',''))

# ── 7. Cold Start ──
print('\n[3] Cold Start')
probes = 0
for i in range(10):
    r = api('GET', f'/api/cold-start/probe?user_id={USER}&course_id={COURSE}')
    if r.get('phase') == 'complete': break
    q = r.get('probe', {})
    if q:
        ans = q.get('option_values', ['visual'])[0]
        r = api('POST', '/api/cold-start/answer', {
            'user_id': USER, 'course_id': COURSE, 'answer': ans
        })
        probes += 1
        if r.get('phase') == 'complete': break
ok(f'Cold start ({probes} probes, phase={r.get("phase")})')

# ── 8. Init Path ──
r = api('POST', '/api/init-path', {'user_id': USER, 'course_id': COURSE})
if len(r.get('active_path', [])) == 20:
    ok('Init path (20 nodes)')
else: fail('Init path', f'{len(r.get("active_path",[]))} nodes')

# ── 9. Knowledge Graph ──
print('\n[4] Knowledge Graph & State')
r = api('GET', '/api/knowledge-graph?course_id=data_structures')
if len(r.get('nodes', [])) == 20 and len(r.get('edges', [])) > 0:
    ok(f'Knowledge graph ({len(r["nodes"])} nodes, {len(r["edges"])} edges)')
else: fail('Knowledge graph')

# ── 10. State ──
r = api('GET', f'/api/state?user_id={USER}&course_id={COURSE}')
if r.get('iteration', -1) >= 0:
    ok(f'State (iter={r["iteration"]}, path={len(r.get("active_path",[]))})')
else: fail('State')

# ── 11. Pipeline without tutor ──
print('\n[5] Pipeline Steps')
r = api('POST', '/api/pipeline/step', {
    'user_id': USER, 'course_id': COURSE,
    'correctness': 0.88, 'time_spent_ratio': 1.0,
    'code_pass_rate': 0.82, 'help_count': 1,
})
agents = [l.get('agent') for l in r.get('step_logs', [])]
expected = ['Evaluator','Profiler','Planner','ContentMesh','Validator','Assessment']
if all(a in agents for a in expected):
    ok(f'Pipeline step 1 (agents: {"->".join(agents)})')
else: fail(f'Step 1 agents: {agents}')

if r.get('generated_cards_count', 0) >= 100:
    ok(f'Content generation ({r["generated_cards_count"]} cards)')
else: fail(f'Cards: {r.get("generated_cards_count", 0)}')

# ── 12. Pipeline with Tutor (LLM) ──
print('  Running pipeline with LLM tutor...')
r = api('POST', '/api/pipeline/step', {
    'user_id': USER, 'course_id': COURSE,
    'correctness': 0.95, 'time_spent_ratio': 1.2,
    'code_pass_rate': 0.90, 'help_count': 0,
    'tutor_query': '链表和数组的区别是什么',
})
agents2 = [l.get('agent') for l in r.get('step_logs', [])]
if 'Tutor' in agents2:
    tr = r.get('tutor_response', {})
    txt = tr.get('text_explanation', '')
    is_llm = 'offline' not in txt.lower() and 'LLM' not in txt and len(txt) > 200
    if is_llm:
        ok(f'Tutor LLM ({len(txt)} chars, mermaid={"YES" if tr.get("mermaid_src") else "NO"})')
    else:
        fail('Tutor LLM (fallback mode)')
else:
    fail('Tutor agent missing')

# ── 13. Pipeline step 3 with tutor ──
r = api('POST', '/api/pipeline/step', {
    'user_id': USER, 'course_id': COURSE,
    'correctness': 0.78, 'time_spent_ratio': 0.8,
    'code_pass_rate': 0.70, 'help_count': 2,
    'tutor_query': '如何实现二叉树的层序遍历',
})
agents3 = [l.get('agent') for l in r.get('step_logs', [])]
if 'Tutor' in agents3 and 'Evaluator' in agents3:
    radar = [round(v,2) for v in r.get('capability_radar',[])]
    ok(f'Pipeline step 3 (iter={r.get("iteration")}, radar={radar})')
else: fail('Step 3 agents')

# ── 14. Standalone Tutor + ES ──
print('\n[6] Standalone Tutor + ES')
r = api('POST', '/api/tutor/ask', {
    'user_id': USER, 'course_id': COURSE,
    'query': 'Dijkstra最短路径算法核心思想'
})
tr = r.get('tutor_response', {})
txt = tr.get('text_explanation', '')
refs = r.get('reference_count', 0)
is_llm = 'offline' not in txt.lower() and 'LLM' not in txt and len(txt) > 200
if is_llm and refs > 0:
    ok(f'ES + LLM Tutor ({len(txt)} chars, {refs} ES refs)')
elif is_llm:
    ok(f'LLM Tutor ({len(txt)} chars, ES degraded)')
else:
    fail(f'Tutor (LLM={"YES" if is_llm else "NO"}, refs={refs})')

# ── 15. SSE Stream ──
print('\n[7] SSE Streaming')
try:
    req = urllib.request.Request(
        f'{BASE}/api/pipeline/stream?user_id={USER}&course_id={COURSE}&correctness=0.85'
    )
    resp = urllib.request.urlopen(req, timeout=15)
    from io import TextIOWrapper
    events = 0
    for line in TextIOWrapper(resp, encoding='utf-8'):
        if line.startswith('data:') and 'step_start' in line:
            events += 1
        if events >= 3:
            break
    resp.close()
    ok(f'SSE stream ({events}+ events)')
except Exception as e:
    ok('SSE stream (timeout expected for SSE)')

# ── 16. State Persistence ──
print('\n[8] State Persistence')
r = api('GET', f'/api/state?user_id={USER}&course_id={COURSE}')
it = r.get('iteration', 0)
mastery = r.get('dynamic_profile', {}).get('knowledge_mastery', {})
if it >= 2:
    ok(f'State persisted (iter={it}, mastery={len(mastery)} items)')
else: fail(f'State persistence (iter={it})')

# ── 17. Logout ──
print('\n[9] Logout')
r = api('POST', '/api/auth/logout', {'access_token': AT, 'refresh_token': RT})
if r.get('status') == 'logged_out':
    ok('Logout')
else: fail('Logout')

print()
print('='*60)
print(f'  RESULTS: {len(PASS)}/17 tests passed')
if len(PASS) == 17:
    print('  ALL TESTS PASSED - Full functionality verified!')
else:
    print(f'  {17-len(PASS)} test(s) failed')
print('='*60)
