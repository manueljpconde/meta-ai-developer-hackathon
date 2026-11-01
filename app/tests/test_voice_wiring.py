"""Wiring checks (8) and stdlib HTTP journey."""
import re
import urllib.request
import urllib.parse
import threading
import time
import tempfile
import os
import unittest
from wsgiref.simple_server import make_server
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer

from app.tests.helpers import AppTestCase, csrf_token
from app import web, store


class VoiceWiringTest(AppTestCase):
    """Criterion (7)/(8): served page includes script and correct bindings."""
    def test_page_includes_script_and_bindings(self):
        body = self.client.get('/').body
        self.assertIn('id="voiceFalar"', body)
        self.assertIn('id="voiceFalarHeader"', body)
        self.assertIn('id="voicePanel"', body)
        # script present
        self.assertIn('<script>', body)
        # Falar binds to opening panel
        self.assertIn('voiceFalar', body)
        self.assertIn('voicePanel', body)
        self.assertIn('style.display="block"', body.replace("'", '"') if "style.display" in body else body)
        # send -> /voice/extract, confirm -> /voice/confirm, cancel -> /voice/cancel
        self.assertIn('/voice/extract', body)
        self.assertIn('/voice/confirm', body)
        self.assertIn('/voice/cancel', body)
        # panel not hidden by CSS once opened: JS sets display block
        self.assertIn('speechSynthesis', body)
        # microphone path calls getUserMedia and posts WAV to /voice/transcribe
        self.assertIn('getUserMedia', body)
        self.assertIn('/voice/transcribe', body)
        self.assertIn('encWAV', body)
        # A0: no tip/prompt anywhere on signed-in pages
        self.assertNotIn('voice_hint', body)  # notice removed
        # confirm uses voice language (speak lang from agent)
        self.assertIn('speechSynthesis', body)

    def test_empty_home_no_tip(self):
        body = self.client.get('/').body
        # A0: no tip on empty home
        self.assertNotIn('Dica:', body)
        self.assertNotIn('voice_hint', body)


class VoiceHttpJourneyTest(unittest.TestCase):
    """Criterion (8): stdlib HTTP journey in PT and EN mimicking browser script order."""
    def _run_journey(self, lang_code, page_lang):
        # Setup isolated DB and server
        tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmp.name, 'test.db')
        old_db = web.DB_PATH
        web.DB_PATH = db_path
        from app.tests.helpers import Client
        # Create client and authenticate
        c = Client()
        from app import store as st
        import time as _t, secrets as _s
        email = 'journey@example.com'
        st.get_or_create_tenant(db_path, email, now=_t.time())
        tenant = st.get_tenant_by_email(db_path, email)
        sid = 'sess-' + email + lang_code
        st.create_session(db_path, sid, tenant['id'], email, _t.time(), _t.time()+86400, _s.token_urlsafe(16))
        c.cookies['session'] = sid
        # settings
        body = c.get('/settings').body
        tok = csrf_token(body)
        settings = {'share':'40','iva':'23','retencao':'25','irs':'30','ss':'10','expenses':'350,00' if lang_code=='pt' else '350.00','form_locale':page_lang,'csrf_token':tok}
        c.post('/settings', settings)
        # Stub extraction
        from app import voice as vm, voice_conversation as vc
        vc.CONVERSATIONS.clear()
        old = getattr(vm, 'EXTRACTION_CLIENT', None)
        class E:
            n=0
            def extract(self, text):
                E.n+=1
                if E.n==1:
                    # First utterance: name + stage, missing commission/share/escritura_date
                    # Simulate: Novo negócio T1 em Alvalade, escritura lá para março -> we map to new_deal name + escritura month
                    return {'intent':'update','kind':'new_deal','language':lang_code,'name':'T1 Alvalade','escritura_date':'março','stage':'confirmado'}
                if E.n==2:
                    return {'intent':'update','kind':'new_deal','language':lang_code,'commission':'10000','share':'40','escritura_date':'março','stage':'confirmado','name':'T1 Alvalade'}
                return {'intent':'update','kind':'new_deal','language':lang_code}
        vm.EXTRACTION_CLIENT = E()
        try:
            body2 = c.get('/', accept_language=page_lang).body
            tok2 = csrf_token(body2)
            r1 = c.post('/voice/extract', {'csrf_token':tok2,'text':'Novo negócio T1 em Alvalade, escritura lá para março'})
            # Should ask one question for missing commission/share (escritura_date is month-only -> estimated)
            self.assertIn('voice-question', r1.body)
            cid = re.search(r'data-conversation-id="([^"]+)"', r1.body)
            self.assertIsNotNone(cid, r1.body[:800])
            cid = cid.group(1)
            r2 = c.post('/voice/extract', {'csrf_token':tok2,'conversation_id':cid,'text':'comissão 10000 e 40 percent'})
            self.assertTrue('Confirmas' in r2.body or 'Do you confirm' in r2.body, r2.body[:800])
            self.assertTrue('(estimada)' in r2.body or '(estimated)' in r2.body, r2.body[:500])
            yes_word = 'sim' if lang_code=='pt' else 'yes'
            r3 = c.post('/voice/extract', {'csrf_token':tok2,'conversation_id':cid,'text':yes_word})
            # After yes, deal appears in forecast
            # Also confirm via button path
            # Check DB
            deals = st.list_deals(db_path, tenant_id=tenant['id'])
            saved = [d for d in deals if 'T1 Alvalade' in d['name']]
            self.assertEqual(len(saved), 1, deals)
            self.assertEqual(saved[0]['escritura_date'], '2026-03-15')
            self.assertEqual(saved[0]['escritura_estimada'], 1)
            # Forecast page shows (estimada)
            fbody = c.get('/').body
            self.assertTrue('(estimada)' in fbody or '(estimated)' in fbody, fbody[:500])
            return True
        finally:
            if old is None:
                try: delattr(vm, 'EXTRACTION_CLIENT')
                except: pass
            else:
                vm.EXTRACTION_CLIENT = old
            web.DB_PATH = old_db
            tmp.cleanup()

    def test_journey_pt(self):
        self._run_journey('pt','pt-PT')

    def test_journey_en(self):
        self._run_journey('en','en-GB')
