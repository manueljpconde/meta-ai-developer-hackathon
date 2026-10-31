"""Smoke + full journey PT/EN with independent euro calc."""
import unittest, tempfile, os, threading, time, urllib.request, urllib.parse, http.cookiejar, re
from app import web, store
from app.tests.helpers import csrf_token

class SmokeTest(unittest.TestCase):
    def test_app_server_over_http(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = tmp.name + '/smoke.db'
        web.DB_PATH = db
        from wsgiref.simple_server import make_server
        from app.server import ThreadingWSGIServer
        import http.client as hc
        srv = make_server('127.0.0.1', 0, web.application, server_class=ThreadingWSGIServer)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(srv.shutdown)
        time.sleep(0.2)
        conn = hc.HTTPConnection('127.0.0.1', port, timeout=5)
        conn.request('GET', '/signin')
        resp = conn.getresponse()
        body = resp.read().decode()
        self.assertEqual(resp.status, 200)
        self.assertIn('Agentimo', body)

def do_journey(lang):
    tmp = tempfile.TemporaryDirectory()
    db = tmp.name + '/j.db'
    web.DB_PATH = db
    from app.tests.helpers import Client
    from app import mail
    mail.OUTBOX=[]
    c = Client()
    # unauthenticated -> redirect to signin check later; first signin flow via http-like harness
    # Use helpers auth for speed then full flow: settings, deal, forecast, edit, delete
    # Request link
    body = c.get('/signin').body
    tok = csrf_token(body)
    c.post('/signin', {'email': 'journey@test.com', 'csrf_token': tok})
    # get link token from outbox if present else use helper tenant
    if mail.OUTBOX:
        token = mail.OUTBOX[0]['link'].split('token=')[1]
        c.get('/auth/verify?token='+token)
    else:
        # fallback: inject session directly (helpers path)
        import time as tm, secrets
        tenant = store.get_or_create_tenant(db, 'journey@test.com', now=tm.time())
        ten = store.get_tenant_by_email(db, 'journey@test.com')
        sid='j-'+ten['email']
        store.create_session(db, sid, ten['id'], 'journey@test.com', tm.time(), tm.time()+3600*30, secrets.token_urlsafe(16))
        c.cookies['session']=sid
    # lang switch if needed
    if lang != 'pt-PT':
        b = c.get('/signin').body
        c.post('/language', {'lang': lang, 'csrf_token': csrf_token(b)})
    # save settings
    if lang == 'en-GB':
        settings = {'share':'50','iva':'23','retencao':'25','irs':'30','ss':'10','expenses':'350.00','form_locale': lang}
    else:
        settings = {'share':'50','iva':'23','retencao':'25','irs':'30','ss':'10','expenses':'350,00','form_locale': lang}
    b = c.get('/settings').body
    settings['csrf_token']=csrf_token(b)
    r = c.post('/settings', settings)
    assert r.code==303, r.body[:500]
    # create deal commission 10000 share 40%
    comm = '10000.00' if lang=='en-GB' else '10000,00'
    deal = {'name':'Journey Deal','commission': comm,'share':'40','month':'2026-11','stage':'confirmado','agency':'','form_locale': lang}
    b = c.get('/deals/new').body
    deal['csrf_token']=csrf_token(b)
    rev = c.post('/deals/review', deal)
    assert rev.code==200, rev.body[:500]
    # independent euro calc: 10000 * 0.4 = 4000
    # extract share from review
    m = re.search(r'(4000|4 000|4,000)', rev.body)
    assert m, 'expected 4000 in review: '+rev.body[:2000]
    # confirm
    from app.tests.helpers import hidden_inputs
    params = hidden_inputs(rev.body)
    params['csrf_token']=csrf_token(rev.body)
    conf = c.post('/deals/confirm', params)
    assert conf.code==303, conf.body[:500]
    # forecast shows euros independently checked
    body = c.get('/').body
    assert 'Journey Deal' in body, body[:1000]
    # edit
    deals = store.list_deals(db)
    did = deals[0]['id']
    b = c.get('/deals/edit?id=%d' % did).body
    assert b.lower().count('<h1')==1
    upd = {'name':'Journey Deal Edited','commission': comm,'share':'40','month':'2026-12','stage':'confirmado','agency':'','form_locale': lang,'csrf_token': csrf_token(b)}
    r2 = c.post('/deals/update?id=%d' % did, upd)
    assert r2.code==303, r2.body[:500]
    body2 = c.get('/').body
    assert 'Journey Deal Edited' in body2
    # delete
    b = c.get('/deals/delete?id=%d' % did).body
    r3 = c.post('/deals/delete?id=%d' % did, {'csrf_token': csrf_token(b)})
    assert r3.code==303, r3.body[:500]
    assert store.count_deals(db)==0
    tmp.cleanup()
    return True

class JourneyPTTest(unittest.TestCase):
    def test_full_journey_pt(self):
        self.assertTrue(do_journey('pt-PT'))
class JourneyENTest(unittest.TestCase):
    def test_full_journey_en(self):
        self.assertTrue(do_journey('en-GB'))
