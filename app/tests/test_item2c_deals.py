"""Deal edit/delete tenant-scoped, unit labels, implausible handling."""
from app.tests.helpers import AppTestCase, csrf_token, DEAL_PT
from app import web, store

class DealEditTest(AppTestCase):
    def test_forecast_links_to_edit_and_delete_with_confirmation(self):
        self.save_settings()
        rev = self.review()
        self.confirm(rev.body)
        body = self.client.get('/').body
        self.assertIn('/deals/edit?id=', body)
        deals = store.list_deals(self.db_path)
        edit_body = self.client.get('/deals/edit?id=%d' % deals[0]['id']).body
        self.assertIn('deal_edit_title', edit_body)
        self.assertIn('/deals/delete?id=', edit_body)
        del_body = self.client.get('/deals/delete?id=%d' % deals[0]['id']).body
        self.assertIn('delete_deal_confirm', del_body.lower() + del_body)
        # confirm delete
        resp = self.client.post('/deals/delete?id=%d' % deals[0]['id'], {'csrf_token': csrf_token(del_body)})
        self.assertEqual(resp.code, 303)
        self.assertEqual(self.deal_count(), 0)
        self.assertNotIn(deals[0]['name'], self.client.get('/').body)
    def test_tenant_isolation_edit_delete(self):
        self.save_settings()
        rev = self.review()
        self.confirm(rev.body)
        deals = store.list_deals(self.db_path)
        did = deals[0]['id']
        # create second tenant
        import tempfile, time
        from app import store as st
        tmp = self.db_path
        # create second client with different tenant
        from app.tests.helpers import Client
        import secrets
        c2 = Client()
        # manually create tenant2
        t2 = st.get_or_create_tenant(tmp, 'other@x.com', now=time.time())
        tenant2 = st.get_tenant_by_email(tmp, 'other@x.com')
        sid2 = 'sess-other'
        st.create_session(tmp, sid2, tenant2['id'], 'other@x.com', time.time(), time.time()+3600*30, secrets.token_urlsafe(16))
        c2.cookies['session']=sid2
        # other tenant should 404 on edit/delete
        r = c2.get('/deals/edit?id=%d' % did)
        self.assertEqual(r.code, 404)
        self.assertEqual(st.count_deals(tmp), 1)
        r2 = c2.request('POST', '/deals/delete?id=%d' % did, params={'csrf_token': 'x'})
        self.assertEqual(r2.code, 404)
        self.assertEqual(st.count_deals(tmp), 1)
    def test_edit_validates_and_updates(self):
        self.save_settings()
        rev = self.review()
        self.confirm(rev.body)
        deals = store.list_deals(self.db_path)
        did = deals[0]['id']
        body = self.client.get('/deals/edit?id=%d' % did).body
        params = {'name': 'Updated', 'commission': '20000,00', 'share': '40', 'month': '2026-12', 'stage': 'provavel', 'agency': '', 'form_locale': 'pt-PT', 'csrf_token': csrf_token(body)}
        resp = self.client.post('/deals/update?id=%d' % did, params)
        self.assertEqual(resp.code, 303)
        updated = store.get_deal(self.db_path, did, store.get_tenant_by_email(self.db_path, 'test@example.com')['id'])
        self.assertEqual(updated['name'], 'Updated')

class UnitLabelTest(AppTestCase):
    def test_forms_label_units(self):
        body = self.client.get('/settings').body
        self.assertIn('(€)', body)  # euro sign
        self.assertIn('(%)', body)
        body2 = self.client.get('/deals/new').body
        self.assertIn('(€)', body2)
        self.assertIn('(%)', body2)

class ImplausibleInputTest(AppTestCase):
    def test_share_4_refused_without_confirmation(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params['share']='4'
        r = self.review(values=params)
        self.assertEqual(r.code, 200)
        self.assertIn('4 em vez de 40', r.body + r.body.lower())
        self.assertEqual(self.deal_count(), 0)
    def test_share_4_allowed_with_confirm_flag(self):
        self.save_settings()
        body = self.client.get('/deals/new').body
        params = dict(DEAL_PT)
        params['share']='4'
        params['confirm_share']='1'
        params['csrf_token']=csrf_token(body)
        r = self.client.post('/deals/review', params)
        self.assertEqual(r.code, 200)
        # should not show err_confirm_share
        self.assertNotIn('4 em vez de 40', r.body)
    def test_small_commission_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params['commission']='50,00'
        r = self.review(values=params)
        self.assertEqual(r.code, 200)
        self.assertIn('100', r.body)
    def test_negative_amount_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params['commission']='-100,00'
        r = self.review(values=params)
        self.assertEqual(r.code, 200)
        self.assertIn('negativo', r.body.lower())
    def test_empty_amount_refused(self):
        self.save_settings()
        params = dict(DEAL_PT)
        params['commission']=''
        r = self.review(values=params)
        self.assertEqual(r.code, 200)
        self.assertEqual(self.deal_count(), 0)
    def test_negative_expenses_refused_in_settings(self):
        body = self.client.get('/settings').body
        params = {'share':'50','iva':'23','retencao':'25','irs':'30','ss':'10','expenses':'-100,00','form_locale':'pt-PT','csrf_token': csrf_token(body)}
        r = self.client.post('/settings', params)
        self.assertEqual(r.code, 200)
        self.assertIn('negativo', r.body.lower())
