"""Hosted runtime is explicit, origin constrained, and protected by default."""
import contextlib
import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app import __version__
from app.server import make_server
from run import runtime_options

PASSWORD = 'test-only-long-password-87'
ORIGIN = 'https://puzzle.example.test'

class HostedConfigurationTests(unittest.TestCase):
    def test_local_runtime_defaults_and_explicit_cli(self):
        self.assertEqual(runtime_options([], {}), {'port':8765,'data_dir':None})
        self.assertEqual(runtime_options(['--port','9000','--data-dir','/tmp/puzzles'],{})['port'],9000)
        self.assertEqual(runtime_options([],{'PORT':'9999','CODEWORD_ACCESS_PASSWORD':PASSWORD}), {'port':8765,'data_dir':None})

    def test_version_flag_reports_release(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
            runtime_options(['--version'], {})
        self.assertEqual(stop.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), 'Codeword Workbench ' + __version__)
        self.assertRegex(__version__, r'^\d+\.\d+\.\d+$')

    def test_hosted_runtime_env_and_cli_override(self):
        options=runtime_options([],{'CODEWORD_HOSTED':'1','PORT':'8088','RAILWAY_PUBLIC_DOMAIN':'puzzle.example.test','CODEWORD_ACCESS_PASSWORD':PASSWORD})
        self.assertEqual(options['host'],'0.0.0.0');self.assertEqual(options['port'],8088)
        self.assertEqual(options['public_origin'],ORIGIN);self.assertEqual(str(options['data_dir']),'/data')
        self.assertEqual(options['access_password'],PASSWORD);self.assertFalse(options['allow_public'])
        self.assertEqual(runtime_options(['--port','9090'],{'CODEWORD_HOSTED':'1'})['port'],9090)

    def test_nonloopback_requires_origin_and_strong_access_choice(self):
        cases=[{}, {'public_origin':ORIGIN}, {'public_origin':'http://puzzle.example.test','access_password':PASSWORD}, {'public_origin':ORIGIN,'access_password':'short'}, {'public_origin':ORIGIN,'access_password':' '*30}]
        for options in cases:
            with self.subTest(options={k:v for k,v in options.items() if k!='access_password'}),self.assertRaises(ValueError):
                make_server(0,host='0.0.0.0',**options)

    def test_origin_must_be_bare_https_without_credentials_or_suffix(self):
        for origin in ['https://user@puzzle.example.test','https://@puzzle.example.test','https://puzzle%2F.example.test','https://puzzle.example.test?','https://puzzle.example.test/path','https://puzzle.example.test?x=1','https://puzzle.example.test#x','https://puzzle.example.test:bad','https://','https://puzzle.example.test\n.evil']:
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                make_server(0,host='0.0.0.0',public_origin=origin,access_password=PASSWORD)

class HostedClient:
    """One browser: keeps cookies between requests, like the app does."""
    def __init__(self,server):
        self.server=server;self.cookies={}
    def request(self,path='/',method='GET',body=None,host='puzzle.example.test',origin=None,cookies=True):
        headers={'Host':host}
        if origin is not None:headers['Origin']=origin
        if body is not None:headers['Content-Type']='application/json'
        if cookies and self.cookies:headers['Cookie']='; '.join(f'{k}={v}' for k,v in self.cookies.items())
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        conn.request(method,path,json.dumps(body) if body is not None else None,headers);response=conn.getresponse()
        raw=response.read();status=response.status
        for header in response.headers.get_all('Set-Cookie') or []:
            name,value=header.split(';',1)[0].split('=',1)
            if 'Max-Age=0' in header:self.cookies.pop(name,None)
            else:self.cookies[name]=value
        result=(status,dict(response.getheaders()),raw);conn.close();return result
    def json(self,*args,**kwargs):
        status,_,raw=self.request(*args,**kwargs);return status,json.loads(raw)
    def login(self,password=PASSWORD):
        return self.json('/api/login','POST',{'password':password})

def puzzle():
    return {'name':'Hosted fixture','language':'en','rows':1,'cols':3,'useDictionary':True,
            'cells':[{'black':False,'number':str(i+1),'letter':''} for i in range(3)],'rules':{'maxLettersPerNumber':1,'uniqueLetters':True}}

class HostedServerCase(unittest.TestCase):
    options={'access_password':PASSWORD}
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=make_server(0,self.temp.name,public_origin=ORIGIN,**self.options)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=HostedClient(self.server)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

class PasswordOnlyTests(HostedServerCase):
    def test_data_routes_require_sign_in_without_browser_prompt(self):
        for path in ['/api/health','/api/puzzles','/api/autosave','/api/dictionaries/fi','/api/solve-jobs/'+'a'*32]:
            with self.subTest(path=path):
                status,headers,body=self.client.request(path)
                self.assertEqual(status,401);self.assertNotIn('WWW-Authenticate',headers);self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertNotIn('ocrAvailable',body.decode());self.assertTrue(json.loads(body)['signIn'])
        for method in ['POST','PUT','PATCH','DELETE','HEAD','OPTIONS']:
            self.assertEqual(self.client.request('/api/puzzles',method)[0],401)
    def test_app_shell_and_session_state_are_open(self):
        self.assertEqual(self.client.request('/')[0],200);self.assertEqual(self.client.request('/app.js')[0],200)
        status,info=self.client.json('/api/session')
        self.assertEqual(status,200);self.assertEqual(info['mode'],'signed-out')
        self.assertFalse(info['guestAccess']);self.assertTrue(info['userLogin'])
    def test_password_sign_in_and_sign_out(self):
        for wrong in ['wrong',PASSWORD+'x','',None,123]:
            status,result=self.client.login(wrong)
            self.assertEqual(status,401);self.assertNotIn('cw_user',self.client.cookies)
        status,info=self.client.login()
        self.assertEqual(status,200);self.assertEqual(info['mode'],'user');self.assertIn('cw_user',self.client.cookies)
        self.assertEqual(self.client.request('/api/puzzles')[0],200)
        self.assertEqual(self.client.json('/api/session')[1]['mode'],'user')
        status,info=self.client.json('/api/logout','POST',{})
        self.assertEqual(info['mode'],'signed-out');self.assertNotIn('cw_user',self.client.cookies)
        self.assertEqual(self.client.request('/api/puzzles')[0],401)
    def test_session_cookie_attributes_and_forgery(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request('POST','/api/login',json.dumps({'password':PASSWORD}),{'Host':'puzzle.example.test','Content-Type':'application/json'})
        response=conn.getresponse();response.read();cookie=response.getheader('Set-Cookie');conn.close()
        for attribute in ['HttpOnly','Secure','SameSite=Strict','Path=/','Max-Age=']:
            self.assertIn(attribute,cookie)
        token=cookie.split(';',1)[0].split('=',1)[1];expires,nonce,signature=token.split('.')
        for forged in [f'{int(expires)+1}.{nonce}.{signature}',f'{expires}.{"b"*32}.{signature}',f'{expires}.{nonce}.{"0"*64}',f'1.{nonce}.{signature}','garbage','']:
            with self.subTest(forged=forged):
                self.assertEqual(HostedClient(self.server).request('/api/puzzles',cookies=False)[0],401)
                other=HostedClient(self.server);other.cookies={'cw_user':forged}
                self.assertEqual(other.request('/api/puzzles')[0],401)
        valid=HostedClient(self.server);valid.cookies={'cw_user':token}
        self.assertEqual(valid.request('/api/puzzles')[0],200)
    def test_wrong_passwords_are_rate_limited(self):
        for _ in range(10):self.assertEqual(self.client.login('wrong-password')[0],401)
        self.assertEqual(self.client.login('wrong-password')[0],429)
        self.assertEqual(self.client.login()[0],429)
    def test_exact_get_health_exception_only(self):
        status,headers,body=self.client.request('/healthz',host='healthcheck.railway.app')
        self.assertEqual(status,200);self.assertEqual(json.loads(body),{'ok':True})
        for path in ['/healthz?query=1','/healthz/','/%68ealthz']:
            self.assertIn(self.client.request(path)[0],(401,404))
        for method in ['POST','HEAD','OPTIONS']:
            self.assertEqual(self.client.request('/healthz',method)[0],401)
    def test_duplicate_security_headers_fail_closed(self):
        self.client.login()
        cookie='cw_user='+self.client.cookies['cw_user']
        for name,value in [('Host','puzzle.example.test'),('Origin',ORIGIN),('Cookie',cookie)]:
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            conn.putrequest('GET','/api/puzzles',skip_host=True)
            conn.putheader('Host','puzzle.example.test');conn.putheader('Cookie',cookie)
            if name=='Origin':conn.putheader('Origin',ORIGIN)
            conn.putheader(name,value);conn.endheaders();response=conn.getresponse()
            self.assertIn(response.status,(401,403));response.read();conn.close()
    def test_spoofed_host_or_origin_fails_even_when_signed_in(self):
        self.client.login()
        for host in ['evil.test','puzzle.example.test.evil','puzzle.example.test:443','127.0.0.1']:
            self.assertEqual(self.client.request(host=host)[0],403)
        for origin in ['https://evil.test','http://puzzle.example.test','null',ORIGIN+'/']:
            for method in ['GET','POST']:
                self.assertEqual(self.client.request('/api/puzzles',method,origin=origin)[0],403)
            self.assertEqual(self.client.request('/api/login','POST',{'password':PASSWORD},origin=origin)[0],403)
        self.assertEqual(self.client.request('/api/puzzles',origin=ORIGIN)[0],200)
    def test_changing_the_password_ends_sessions(self):
        self.client.login();token=self.client.cookies['cw_user']
        other=make_server(0,self.temp.name,public_origin=ORIGIN,access_password=PASSWORD+'-changed')
        thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
        try:
            client=HostedClient(other);client.cookies={'cw_user':token}
            self.assertEqual(client.request('/api/puzzles')[0],401)
        finally:other.shutdown();other.server_close();thread.join()

class GuestAndUserTests(HostedServerCase):
    options={'access_password':PASSWORD,'allow_public':True}
    def test_guest_mode_by_default_without_saved_puzzles(self):
        status,info=self.client.json('/api/session')
        self.assertEqual(info['mode'],'guest');self.assertTrue(info['guestAccess']);self.assertTrue(info['userLogin'])
        self.assertEqual(self.client.request('/api/health')[0],200)
        for path,method,body in [('/api/puzzles','GET',None),('/api/puzzles','POST',puzzle()),('/api/puzzles/'+'a'*32,'GET',None),
                                 ('/api/puzzles/'+'a'*32,'DELETE',None),('/api/autosave','GET',None),('/api/autosave','PUT',{'puzzle':puzzle(),'unsaved':True})]:
            with self.subTest(path=path,method=method):
                status,result=self.client.json(path,method,body)
                self.assertEqual(status,403);self.assertIn('user mode',result['error'])
        self.assertEqual(list((Path(self.temp.name)/'puzzles').iterdir()),[])
        self.assertFalse((Path(self.temp.name)/'autosave.json').exists())
    def test_guests_never_see_or_change_the_persistent_dictionary(self):
        user=HostedClient(self.server);user.login()
        self.assertEqual(user.json('/api/dictionaries/en','PUT',{'words':['SHARED','SECRET']})[0],200)
        status,data=self.client.json('/api/dictionaries/en')
        self.assertEqual(status,200);self.assertNotIn('SECRET',data['words']);self.assertIn('bundled demonstration',data['source'])
        self.assertEqual(self.client.json('/api/dictionaries/en/search?q=SEC')[1]['total'],0)
        status,result=self.client.json('/api/dictionaries/en/import','POST',{'text':'GUEST\nWORDS\n'})
        self.assertEqual(status,200);self.assertEqual(result['source'],'temporary guest dictionary')
        self.assertEqual(self.client.json('/api/dictionaries/en/entries','POST',{'add':['EXTRA']})[1]['count'],3)
        self.assertEqual(self.client.json('/api/dictionaries/en')[1]['words'],['EXTRA','GUEST','WORDS'])
        self.assertEqual(user.json('/api/dictionaries/en')[1]['words'],['SECRET','SHARED'])
        self.assertFalse(any('GUEST' in path.read_text() for path in Path(self.temp.name).rglob('*.json')))
        other=HostedClient(self.server)
        self.assertNotIn('GUEST',other.json('/api/dictionaries/en')[1]['words'])
        lookup=self.client.json('/api/lookup','POST',{'puzzle':puzzle(),'query':'GUEST'})[1]
        self.assertTrue(lookup['inDictionary'])
        self.assertFalse(other.json('/api/lookup','POST',{'puzzle':puzzle(),'query':'GUEST'})[1]['inDictionary'])
        self.assertFalse(self.client.json('/api/lookup','POST',{'puzzle':puzzle(),'query':'SECRET'})[1]['inDictionary'])
    def test_guest_cookie_is_a_browser_session_cookie(self):
        status,headers,_=self.client.request('/api/dictionaries/en')
        cookie=headers['Set-Cookie']
        self.assertTrue(cookie.startswith('cw_guest='));self.assertNotIn('Max-Age',cookie)
        for attribute in ['HttpOnly','Secure','SameSite=Strict']:self.assertIn(attribute,cookie)
        self.assertNotIn('Set-Cookie',self.client.request('/api/dictionaries/en')[1])
    def test_guest_dictionary_limits(self):
        status,result=self.client.json('/api/dictionaries/en','PUT',{'words':['A']*200_001})
        self.assertEqual(status,400);self.assertIn('200,000',result['error'])
        status,result=self.client.json('/api/dictionaries/en/import','POST',{'text':'WORD\n'*(1024*1024)})
        self.assertEqual(status,400);self.assertIn('4 MB',result['error'])
    def test_guest_solve_jobs_use_the_guest_dictionary(self):
        self.client.json('/api/dictionaries/en/import','POST',{'text':'CAT\n'})
        status,job=self.client.json('/api/solve-jobs','POST',puzzle())
        self.assertEqual(status,202)
        for _ in range(200):
            status,job=self.client.json('/api/solve-jobs/'+job['id'])
            if job['status']!='running':break
            time.sleep(0.05)
        self.assertEqual(job['status'],'completed')
        self.assertEqual(job['result']['solutions'][0]['letters'],['C','A','T'])
    def test_user_mode_uses_the_persistent_workspace(self):
        self.assertEqual(self.client.login()[1]['mode'],'user')
        status,saved=self.client.json('/api/puzzles','POST',puzzle())
        self.assertEqual(status,200);self.assertTrue((Path(self.temp.name)/'puzzles'/(saved['id']+'.json')).exists())
        self.assertEqual(self.client.json('/api/dictionaries/en','PUT',{'words':['KEEP']})[1]['source'],'custom local dictionary')
        self.assertTrue((Path(self.temp.name)/'dictionaries'/'en.json').exists())
        self.assertEqual(self.client.json('/api/logout','POST',{})[1]['mode'],'guest')
        self.assertEqual(self.client.request('/api/puzzles')[0],403)

class GuestOnlyTests(HostedServerCase):
    options={'allow_public':True}
    def test_public_without_password_is_guest_only(self):
        info=self.client.json('/api/session')[1]
        self.assertEqual(info['mode'],'guest');self.assertFalse(info['userLogin'])
        self.assertEqual(self.client.login()[0],400)
        self.assertEqual(self.client.request('/api/puzzles')[0],403)

class GuestWorkspaceTests(unittest.TestCase):
    def test_capacity_idle_expiry_and_cleanup(self):
        from app.server import GuestWorkspaces,GuestCapacityError
        from app.dictionaries import save_dictionary,dictionary_state,_states
        guests=GuestWorkspaces(limit=2,idle_seconds=60)
        try:
            first,second,third='1'*32,'2'*32,'3'*32
            self.assertFalse(guests.path(first).exists())
            save_dictionary('en',['ONE'],guests.path(first,True));save_dictionary('en',['TWO'],guests.path(second,True))
            dictionary_state('en',guests.path(first))
            with self.assertRaises(GuestCapacityError):guests.path(third,True)
            guests.path(third)  # reading needs no slot
            guests.last_used[first]-=120
            save_dictionary('en',['THREE'],guests.path(third,True))
            self.assertFalse((guests.root/first).exists())
            self.assertFalse(any(key[0]==str(guests.root/first) for key in _states))
            with self.assertRaises(ValueError):guests.path('../etc')
        finally:
            guests.close()
        self.assertFalse(guests.root.exists())

    def test_guest_capacity_keeps_a_slot_for_user_mode(self):
        from app.server import GuestCapacity
        shared=threading.BoundedSemaphore(2);guest=GuestCapacity(shared)
        self.assertTrue(guest.acquire());self.assertFalse(guest.acquire())
        self.assertTrue(shared.acquire(blocking=False));shared.release()
        guest.release()
        self.assertTrue(shared.acquire(blocking=False));self.assertTrue(shared.acquire(blocking=False))
        self.assertFalse(guest.acquire());shared.release();shared.release()

class PublicAndLocalHTTPTests(unittest.TestCase):
    def test_local_mode_keeps_full_access_without_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            server=make_server(0,directory);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                self.assertEqual(server.server_address[0],'127.0.0.1')
                host=f'127.0.0.1:{server.server_port}'
                for path in ['/api/puzzles','/api/autosave','/api/session']:
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request('GET',path,headers={'Host':host})
                    response=conn.getresponse();body=json.loads(response.read())
                    self.assertEqual(response.status,200);self.assertIsNone(response.getheader('Set-Cookie'));conn.close()
                self.assertEqual(body['mode'],'local')
            finally:server.shutdown();server.server_close();thread.join()
