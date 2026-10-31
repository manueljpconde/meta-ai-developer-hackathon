"""Signed-out header, compact switch, sign-in polish, check-email, one h1."""
from app.tests.helpers import AppTestCase, csrf_token, Client
from app import web
import tempfile, time, secrets
from app import store as st

def auth_client(db_path):
    c = Client()
    tenant = st.get_or_create_tenant(db_path, 'auth@test.com', now=time.time())
    ten = st.get_tenant_by_email(db_path, 'auth@test.com')
    sid = 'sess-auth-test'
    st.create_session(db_path, sid, ten['id'], 'auth@test.com', time.time(), time.time()+3600*30, secrets.token_urlsafe(16))
    c.cookies['session'] = sid
    return c

class SignedOutHeaderTest(AppTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web.DB_PATH = tmp.name + "/test.db"
        self.client = Client()
    def body(self, path):
        return self.client.get(path).body
    def test_signin_has_only_compact_switch_no_nav(self):
        b = self.body('/signin')
        self.assertNotIn('nav_home', b)
        self.assertIn('PT', b)
        self.assertIn('EN', b)
        self.assertNotIn('Mudar', b)
        self.assertNotIn('Change', b)
        self.assertIn('lang--compact', b)
    def test_every_signed_out_page_has_compact_switch(self):
        for path in ('/signin', '/auth/verify?token=x'):
            b = self.body(path)
            self.assertIn('lang--compact', b, path)
            self.assertIn('PT', b)
    def test_signed_in_header_has_nav_and_compact_switch(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web.DB_PATH = tmp.name + "/t2.db"
        c = auth_client(web.DB_PATH)
        b = c.get('/').body
        self.assertIn('nav_home', b)
        self.assertIn('lang--compact', b)
    def test_menu_absent_when_signed_out_present_when_signed_in(self):
        b_out = self.body('/signin')
        self.assertNotIn('nav_home', b_out)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web.DB_PATH = tmp.name + "/t3.db"
        c = auth_client(web.DB_PATH)
        b_in = c.get('/').body
        self.assertIn('nav_home', b_in)

class SigninPolishTest(AppTestCase):
    def test_signin_has_agentimo_heading_and_prompt(self):
        b = self.client.get('/signin').body
        self.assertIn('Agentimo', b)
        self.assertIn('signin_heading', b)
        self.assertIn('signin_prompt', b)
    def test_signin_prompt_in_both_languages(self):
        b_pt = self.client.get('/signin').body
        self.assertIn('Introduz o teu email', b_pt)
        self.set_language('en-GB')
        b_en = self.client.get('/signin').body
        self.assertIn('Enter your email', b_en)

class CheckEmailPageTest(AppTestCase):
    def _post_signin(self, email='a@b.com'):
        from app import mail
        mail.OUTBOX=[]
        b = self.client.get('/signin').body
        return self.client.post('/signin', {'email': email, 'csrf_token': csrf_token(b)})
    def test_valid_email_shows_check_email_with_15min(self):
        r = self._post_signin('ok@test.com')
        self.assertEqual(r.code, 200)
        self.assertIn('15', r.body)
        self.assertIn('ok@test.com', r.body)
        self.assertIn('check_email', r.body.lower())
    def test_invalid_email_shows_in_page_error_not_bare_403(self):
        r = self._post_signin('bad')
        self.assertEqual(r.code, 200)
        self.assertIn('error', r.body.lower())
    def test_invalid_csrf_shows_err_csrf_in_page_not_bare_403(self):
        self.client.get('/signin')
        r = self.client.post('/signin', {'email': 'a@b.com', 'csrf_token': 'bad'})
        self.assertEqual(r.code, 200)
        self.assertIn('expirou', r.body.lower())
    def test_rate_limit_shows_in_page_error(self):
        from app import mail
        for i in range(5):
            b = self.client.get('/signin').body
            self.client.post('/signin', {'email': 'rl@test.com', 'csrf_token': csrf_token(b)})
        b = self.client.get('/signin').body
        r = self.client.post('/signin', {'email': 'rl@test.com', 'csrf_token': csrf_token(b)})
        self.assertEqual(r.code, 200)
        self.assertIn('Demasiados', r.body)

class OneH1Test(AppTestCase):
    def test_every_page_has_exactly_one_h1(self):
        paths = ['/', '/settings', '/deals/new', '/scenarios/move']
        for p in paths:
            b = self.client.get(p).body
            count = b.lower().count('<h1')
            self.assertEqual(count, 1, '%s has %d h1' % (p, count))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web.DB_PATH = tmp.name + '/t.db'
        c = Client()
        b = c.get('/signin').body
        self.assertEqual(b.lower().count('<h1'), 1, 'signin h1')
        web.DB_PATH = self.db_path
    def test_review_and_edit_have_one_h1(self):
        self.save_settings()
        rev = self.review()
        self.assertEqual(rev.body.lower().count('<h1'), 1)
        self.confirm(rev.body)
        from app import store
        deals = store.list_deals(self.db_path)
        self.assertTrue(deals)
        b = self.client.get('/deals/edit?id=%d' % deals[0]['id']).body
        self.assertEqual(b.lower().count('<h1'), 1)
        b2 = self.client.get('/deals/delete?id=%d' % deals[0]['id']).body
        self.assertEqual(b2.lower().count('<h1'), 1)
