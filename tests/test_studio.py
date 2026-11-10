import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from studio import server, storage
from studio import browser_login
from studio.metrics import calculate, parse_formula, enrich, summarize
from studio.provider import normalize_post, user_id, number
from studio.provider import Provider
from utils.baidu_utils import trans_cookies


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='baijia-tests-')
        self.path_patch = patch.object(storage, 'DATA', Path(self.temp.name))
        self.path_patch.start()
        self.client = TestClient(server.app)
        self.client.__enter__()
        self.uid = self.client.get('/api/workspace').json()['id']

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.path_patch.stop()
        self.temp.cleanup()



    def demo(self):
        self.assertEqual(self.client.post('/api/demo', json={}).status_code, 200)

    def query(self, **kwargs):
        return self.client.post('/api/posts/query', json={'source': 'demo', **kwargs})

    def test_opens_without_login_and_auth_routes_are_removed(self):
        self.assertEqual(self.client.get('/api/workspace').status_code,200)
        self.assertEqual(self.client.get('/api/authors').status_code,200)
        self.assertEqual(self.client.post('/api/auth/login',json={'name':'old','password':'old-password'}).status_code,404)
        self.assertEqual(self.client.post('/api/auth/register',json={'name':'new','password':'new-password'}).status_code,404)
        self.assertEqual(self.client.post('/api/auth/logout',json={}).status_code,404)
        self.assertFalse(self.client.cookies)
        with storage.db() as c:
            self.assertEqual(c.execute('SELECT password FROM accounts').fetchone()[0],'')

    def test_local_origin_guards(self):
        with TestClient(server.app) as other:
            self.assertEqual(other.get('/api/workspace').json()['id'],self.uid)
        self.assertEqual(self.client.post('/api/demo',json={},headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(self.client.post('/api/demo',content='{}',headers={'Content-Type':'text/plain'}).status_code,415)

    def test_manual_opens_in_desktop_or_falls_back_to_browser(self):
        self.assertEqual(self.client.post('/api/manual/open',json={}).json(),{'desktop':False})
        with patch.object(server.app.state,'open_manual',create=True,return_value={'ok':True}) as opener:
            self.assertEqual(self.client.post('/api/manual/open',json={}).json(),{'desktop':True,'ok':True})
            opener.assert_called_once_with()

    def test_demo_is_separate_and_persists_without_session(self):
        self.demo()
        self.demo()
        self.assertEqual(self.query().json()['summary']['count'],144)
        self.assertEqual(self.client.post('/api/posts/query',json={}).json()['summary']['count'],0)
        with TestClient(server.app) as reopened:
            self.assertEqual(reopened.get('/api/workspace').json()['id'],self.uid)
            self.assertEqual(reopened.post('/api/posts/query',json={'source':'demo'}).json()['summary']['count'],144)

    def test_filters_sort_selection_and_dates(self):
        self.demo()
        data = self.query(author='demo-01', sort='views').json()
        self.assertEqual(len(data['posts']),48)
        self.assertEqual(data['posts'][0]['views'],max(p['views'] for p in data['posts']))
        ids=[p['id'] for p in data['posts'][:3]]
        selected=self.query(author='demo-01',selected=ids).json()
        self.assertEqual(selected['summary']['count'],3)
        self.assertEqual(selected['summary']['totals']['views'],sum(p['views'] for p in data['posts'][:3]))
        self.assertEqual(self.query(selected=[]).json()['summary']['count'],0)
        day=data['posts'][0]['published'][:10]
        self.assertTrue(all(p['published'][:10]==day for p in self.query(start=day,end=day).json()['posts']))
        self.assertEqual(self.query(start='2026-12-31',end='2026-01-01').status_code,400)
        self.assertEqual(self.query(sort='views; DROP TABLE posts').status_code,400)

    def test_calculator_crud_sort_export(self):
        self.demo()
        body={'name':'score','expression':'likes + comments * 2 + shares * 3','aggregation':'sum'}
        r=self.client.post('/api/calculators',json=body)
        self.assertEqual(r.status_code,200,r.text)
        cid=r.json()['id']
        data=self.query(sort='calc_'+cid).json()
        self.assertGreaterEqual(data['posts'][0]['calc_'+cid],data['posts'][-1]['calc_'+cid])
        self.assertEqual(data['summary']['custom'][0]['coverage'],144)
        r=self.client.post('/api/export',json={'source':'demo','selected':[data['posts'][0]['id']]})
        rows=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),2)
        self.assertIn('score(逐作品)', rows[0])
        self.assertEqual(self.client.put('/api/calculators/'+cid,json={**body,'name':'edited'}).status_code,200)
        self.assertEqual(self.client.request('DELETE','/api/calculators/'+cid,json={}).status_code,200)
        self.assertEqual(len(self.client.get('/api/calculators').json()),0)

    def test_cookie_dpapi_and_validation(self):
        self.assertEqual(self.client.post('/api/platform/cookie',json={'cookie':'BDUSS=abc'}).status_code,400)
        cookie='BDUSS=test-private;Hmery-Time=demo'
        self.assertEqual(self.client.post('/api/platform/cookie',json={'cookie':cookie}).status_code,200)
        self.assertEqual(storage.get_cookie(self.uid),cookie)
        with storage.db() as c:
            encrypted=c.execute('SELECT credential FROM accounts').fetchone()[0]
        self.assertNotIn('test-private',encrypted)
        self.assertNotIn('BDUSS',json.dumps(self.client.get('/api/workspace').json()))

    def test_connected_content_search_still_works(self):
        storage.set_cookie(self.uid,'BDUSS=test; Hmery-Time=test')
        page='''<div class="c-container" mu="https://baijiahao.baidu.com/s?id=123"><h3><a href="https://www.baidu.com/link?url=opaque">中国石油报文章</a></h3></div>'''
        with patch.object(server.browser_login,'search_page',return_value=(page,'https://www.baidu.com/s?wd=test',False)):
            response=self.client.get('/api/search',params={'q':'中国石油报','online':'true'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['online'][0]['id'],'123')
        self.assertEqual(response.json()['warning'],'')
        self.assertNotIn('BDUSS',response.text)
        self.assertEqual(self.client.get('/api/search',params={'q':'中国石油报','mode':'users'}).status_code,422)

    def test_add_monitor_by_homepage_and_deduplicate(self):
        storage.set_cookie(self.uid,'BDUSS=test; Hmery-Time=test')
        profile={'id':'123','name':'监控账号','url':'https://author.baidu.com/home/123','fans':10,'likes':20,'total':30,'uk':'private-routing','version':'v'}
        with patch.object(server.provider,'profile',return_value=profile) as fetch,patch.object(server.browser_login,'search_page',side_effect=AssertionError('account search must not run')):
            first=self.client.post('/api/authors',json={'url':'https://author.baidu.com/home/123/'})
            self.assertEqual(first.status_code,200,first.text)
            self.assertFalse(first.json()['existing'])
            self.assertEqual(first.json()['name'],'监控账号')
            with storage.db() as c:
                c.execute("UPDATE authors SET complete=1,synced='kept' WHERE owner=? AND id='123'",(self.uid,))
            second=self.client.post('/api/authors',json={'url':'https://author.baidu.com/home/123'})
            self.assertTrue(second.json()['existing'])
            self.assertEqual(second.json()['synced'],'kept')
            self.assertEqual(second.json()['complete'],1)
            self.assertEqual(fetch.call_count,1)
        self.assertEqual(len(self.client.get('/api/authors').json()),1)
        self.assertNotIn('private-routing',first.text)

    def test_monitor_link_validation_and_connection(self):
        with patch.object(server.provider,'profile') as fetch:
            self.assertEqual(self.client.post('/api/authors',json={'url':'https://evil.invalid/home/123'}).status_code,400)
            self.assertEqual(self.client.post('/api/authors',json={'url':'https://author.baidu.com/home/123'}).status_code,400)
            self.assertFalse(fetch.called)
        with TestClient(server.app) as other:
            self.assertEqual(other.post('/api/authors',json={'url':'https://author.baidu.com/home/123'}).status_code,400)

    def test_browser_login_captures_only_baidu_cookies(self):
        fake_cookie=[{'domain':'.baidu.com','name':'BDUSS','value':'private-baidu'},
                     {'domain':'author.baidu.com','name':'Hmery-Time','value':'t'},
                     {'domain':'.example.com','name':'SECRET','value':'do-not-copy'}]
        browser_login._sessions[self.uid]={'port':1234,'started':server.time.monotonic(),'navigated':False,'process':None}
        response=io.BytesIO(json.dumps({'webSocketDebuggerUrl':'ws://localhost/test'}).encode())
        with patch.object(browser_login.urllib.request,'urlopen',return_value=response),patch.object(browser_login,'command',return_value={'cookies':fake_cookie}):
            result=browser_login.status(self.uid)
        self.assertEqual(result['status'],'connected')
        self.assertNotIn('SECRET',storage.get_cookie(self.uid))
        self.assertIn('BDUSS=private-baidu',storage.get_cookie(self.uid))
        browser_login._sessions.pop(self.uid)

    def test_csv_formula_injection_is_escaped(self):
        self.demo()
        with storage.db() as c:
            c.execute("UPDATE posts SET title='=HYPERLINK(\"bad\")' WHERE owner=?",(self.uid,))
        result=self.client.post('/api/export',json={'source':'demo'})
        rows=list(csv.reader(io.StringIO(result.content.decode('utf-8-sig'))))
        self.assertTrue(rows[1][1].startswith("'="))

    def setup_job(self):
        storage.set_cookie(self.uid,'BDUSS=test; Hmery-Time=test')
        with storage.db() as c:
            c.execute('INSERT INTO jobs(id,owner,author_id,status,message,created) VALUES (?,?,?,?,?,?)',('job',self.uid,'123','queued','',server.now()))
        return {'id':'123','name':'author','url':'https://author.baidu.com/home/123','fans':1,'likes':2,'total':2,'uk':'uk','version':'v'}

    def test_sync_pagination_dedupe_and_completion(self):
        profile=self.setup_job()
        a={'feed_id':'1','dynamic_id':'101','title':'A','ctime':1700000000}
        b={'feed_id':'2','dynamic_id':'102','title':'B','ctime':1700000001}
        metrics={k:1 for k in server.METRICS}
        pages=[{'list':[a],'hasMore':1,'query':{'ctime':'t1'}},{'list':[a,b],'hasMore':0}]
        with patch.object(server.provider,'profile',return_value=profile),patch.object(server.provider,'page',side_effect=pages) as page,patch.object(server.provider,'detail',return_value=metrics),patch.object(server.time,'sleep'):
            server.sync_author('job',self.uid,profile['url'])
        self.assertEqual(page.call_args_list[1].args[2],('101','t1'))
        job=self.client.get('/api/jobs').json()[0]
        self.assertEqual((job['status'],job['processed'],job['pages']),('completed',2,2))
        self.assertEqual(len(self.client.post('/api/posts/query',json={}).json()['posts']),2)

    def test_sync_partial_never_reports_complete(self):
        profile=self.setup_job()
        with patch.object(server.provider,'profile',return_value=profile),patch.object(server.provider,'page',return_value={'list':[{'feed_id':'1','dynamic_id':'101'}],'hasMore':0}),patch.object(server.provider,'detail',side_effect=ValueError('missing')),patch.object(server.time,'sleep'):
            server.sync_author('job',self.uid,profile['url'])
        self.assertEqual(self.client.get('/api/jobs').json()[0]['status'],'partial')
        self.assertEqual(self.client.get('/api/authors').json()[0]['complete'],0)
        self.assertIsNone(self.client.post('/api/posts/query',json={}).json()['posts'][0]['views'])

    def test_sync_repeated_cursor_stops(self):
        profile=self.setup_job()
        page={'list':[{'feed_id':'1','dynamic_id':'101'}],'hasMore':1,'query':{'ctime':'same'}}
        with patch.object(server.provider,'profile',return_value=profile),patch.object(server.provider,'page',return_value=page),patch.object(server.provider,'detail',return_value={k:0 for k in server.METRICS}),patch.object(server.time,'sleep'):
            server.sync_author('job',self.uid,profile['url'])
        self.assertEqual(self.client.get('/api/jobs').json()[0]['status'],'failed')

    def test_limited_sync_does_not_claim_full_history(self):
        profile=self.setup_job()
        page={'list':[{'feed_id':'1','dynamic_id':'101'},{'feed_id':'2','dynamic_id':'102'}],'hasMore':1,'query':{'ctime':'next'}}
        with patch.object(server.provider,'profile',return_value=profile),patch.object(server.provider,'page',return_value=page),patch.object(server.provider,'detail',return_value={k:0 for k in server.METRICS}),patch.object(server.time,'sleep'):
            server.sync_author('job',self.uid,profile['url'],1)
        job=self.client.get('/api/jobs').json()[0]
        self.assertEqual(job['status'],'sampled')
        self.assertEqual(job['processed'],1)
        self.assertEqual(self.client.get('/api/authors').json()[0]['complete'],0)

    def test_calculator_is_available_after_reopening_without_login(self):
        body={'name':'custom','expression':'views','aggregation':'sum'}
        cid=self.client.post('/api/calculators',json=body).json()['id']
        with TestClient(server.app) as reopened:
            self.assertEqual(reopened.get('/api/calculators').json()[0]['id'],cid)
            self.assertEqual(reopened.put('/api/calculators/'+cid,json={**body,'name':'updated'}).status_code,200)
        self.assertEqual(self.client.get('/api/calculators').json()[0]['name'],'updated')

    def test_legacy_workspace_migration_keeps_data_and_baidu_login(self):
        with storage.db() as c:
            c.execute('INSERT INTO accounts VALUES (?,?,?,?)',('legacy','previous-user','old-hash',None))
            c.execute('INSERT INTO sessions VALUES (?,?,?)',('old-session','legacy',99999999999))
            c.execute('INSERT INTO authors VALUES (?,?,?,?,?,?,?,?,?,?)',('legacy','live','123','旧监控账号','https://author.baidu.com/home/123',1,2,3,'saved',1))
            c.execute('INSERT INTO calculators VALUES (?,?,?,?,?)',('kept-calc','legacy','原统计器','views','average'))
            c.execute("DELETE FROM preferences WHERE key='workspace_owner'")
        storage.set_cookie('legacy','BDUSS=old; Hmery-Time=kept')
        storage.initialize()
        self.assertEqual(self.client.get('/api/workspace').json(),{'id':'legacy','connected':True})
        self.assertEqual(self.client.get('/api/authors').json()[0]['name'],'旧监控账号')
        self.assertEqual(self.client.get('/api/calculators').json()[0]['id'],'kept-calc')
        self.assertEqual(storage.get_cookie('legacy'),'BDUSS=old; Hmery-Time=kept')

class MetricsTest(unittest.TestCase):
    def test_search_parser_uses_official_profile_and_article_urls(self):
        page='''<div class="c-container" mu="https://baijiahao.baidu.com/s?id=77"><h3><a href="https://www.baidu.com/link?url=opaque">测试文章</a></h3></div><a href="https://author.baidu.com/home/123">中国石油报</a><a href="https://evil.invalid/home/456">不可信</a>'''
        p=Provider()
        users=p.parse_search(page,'users',redirects=False)
        self.assertEqual([(u['id'],u['name']) for u in users],[('123','中国石油报')])
        works=p.parse_search(page,'content',redirects=False)
        self.assertEqual(works[0]['id'],'77')
        self.assertEqual(works[0]['title'],'测试文章')

    def test_baidu_user_card_with_span_title_and_redirect(self):
        page='''<div class="c-container"><h3><span>中国石油报 - 百家号</span></h3><a class="user-profile-bar_6HemJ" href="http://www.baidu.com/link?url=opaque">中国石油报 5.8万粉丝 关注</a></div>'''
        p=Provider()
        with patch.object(p,'resolve_search_url',return_value='https://author.baidu.com/home/1595713367276134'):
            users=p.parse_search(page,'users')
        self.assertEqual(users,[{'id':'1595713367276134','name':'中国石油报','url':'https://author.baidu.com/home/1595713367276134','indexed':True}])

    def test_search_redirect_is_restricted_and_does_not_send_cookies(self):
        from studio import provider
        from unittest.mock import Mock
        p=Provider()
        self.assertEqual(p.resolve_search_url('http://127.0.0.1/private'),'')
        response=Mock(headers={'location':'https://author.baidu.com/home/123'})
        with patch.object(provider.requests,'get',return_value=response) as request:
            self.assertEqual(p.resolve_search_url('https://www.baidu.com/link?url=test'),'https://author.baidu.com/home/123')
            self.assertNotIn('cookies',request.call_args.kwargs)
            self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_safe_formula(self):
        for formula in ['__import__("os").system("calc")','views ** 1000','views[0]','[views]','True','1e999','unknown + 2']:
            with self.assertRaises(ValueError,msg=formula):parse_formula(formula)
        self.assertEqual(calculate('(likes + comments * 2) / views * 100',{'likes':8,'comments':1,'views':100}),10)
        self.assertIsNone(calculate('likes/views',{'likes':0,'views':0}))
        self.assertIsNone(calculate('likes + favorites',{'likes':3,'favorites':None}))

    def test_coverage_and_ratio_of_totals(self):
        rows=[enrich(dict(views=100,likes=10,comments=0,shares=0,favorites=0)),enrich(dict(views=900,likes=9,comments=0,shares=0,favorites=0)),enrich(dict(views=500,likes=5,comments=None,shares=0,favorites=0))]
        s=summarize(rows,[{'id':'x','name':'rate','expression':'interactions/views*100','aggregation':'totals'}])
        self.assertEqual(s['totals']['engagement'],1.9)
        self.assertEqual(s['coverage']['interactions'],2)
        self.assertEqual(s['totals']['views'],1500)
        self.assertEqual(s['custom'][0]['value'],1.9)
        self.assertEqual(s['custom'][0]['coverage'],2)

    def test_provider_normalization_and_url_limits(self):
        self.assertEqual(trans_cookies(' a=1;b=2=3; c = 4 '),{'a':'1','b':'2=3','c':'4'})
        for url in ['http://author.baidu.com/home/1','https://evil.invalid/home/1','https://author.baidu.com.evil.invalid/home/1','https://author.baidu.com:8080/home/1']:
            with self.assertRaises(ValueError):user_id(url)
        p=normalize_post({'feed_id':'1','dynamic_content':{'title':'<b>标题</b>','pub_time':1700000000000}},'a')
        self.assertEqual(p['title'],'标题')
        self.assertEqual(p['published'][-6:],'+08:00')
        actual=normalize_post({'feed_id':'42','dynamic_type':'2','dynamic_ctime':1730544044,'itemType':'article',
                               'itemData':{'title':'实际结构','publish_at':'1730544062','url':'https://baijiahao.baidu.com/s?id=42'}},'a')
        self.assertEqual(actual['title'],'实际结构')
        self.assertEqual(actual['published'][:10],'2024-11-02')
        self.assertEqual(actual['kind'],'图文')
        self.assertIsNone(number('1.2万'))
        self.assertEqual(number('12,345'),12345)


if __name__=='__main__':unittest.main()
