"""Hosted runtime is explicit, origin constrained, and protected by default."""
import base64
import http.client
import json
import tempfile
import threading
import unittest

from app.server import make_server
from run import runtime_options

PASSWORD = 'test-only-long-password-87'
ORIGIN = 'https://puzzle.example.test'

class HostedConfigurationTests(unittest.TestCase):
    def test_local_runtime_defaults_and_explicit_cli(self):
        self.assertEqual(runtime_options([], {}), {'port':8765,'data_dir':None})
        self.assertEqual(runtime_options(['--port','9000','--data-dir','/tmp/puzzles'],{})['port'],9000)
        self.assertEqual(runtime_options([],{'PORT':'9999','CODEWORD_ACCESS_PASSWORD':PASSWORD}), {'port':8765,'data_dir':None})

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

class HostedHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=make_server(0,self.temp.name,public_origin=ORIGIN,access_password=PASSWORD)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path='/',method='GET',auth=None,host='puzzle.example.test',origin=None):
        headers={'Host':host}
        if auth is not None:headers['Authorization']=auth
        if origin is not None:headers['Origin']=origin
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request(method,path,headers=headers);response=conn.getresponse();result=(response.status,dict(response.getheaders()),response.read());conn.close();return result
    @staticmethod
    def auth(password=PASSWORD,user='codeword'):
        return 'Basic '+base64.b64encode((user+':'+password).encode()).decode()
    def test_ui_and_api_require_authentication_including_health(self):
        for path in ['/','/app.js','/api/health','/api/puzzles','/api/dictionaries/fi','/api/solve-jobs/'+'a'*32]:
            with self.subTest(path=path):
                status,headers,body=self.request(path)
                self.assertEqual(status,401);self.assertIn('Basic',headers['WWW-Authenticate']);self.assertEqual(headers['Cache-Control'],'no-store')
                self.assertNotIn('ocrAvailable',body.decode())
        for method in ['POST','PUT','PATCH','DELETE','HEAD','OPTIONS']:
            self.assertEqual(self.request('/api/puzzles',method)[0],401)
    def test_good_credentials_and_invalid_credentials(self):
        self.assertEqual(self.request(auth=self.auth())[0],200)
        self.assertEqual(self.request('/api/puzzles',auth=self.auth())[0],200)
        for auth in [self.auth('wrong'),self.auth(user='wrong'),'Basic invalid!','Bearer token','Basic '+base64.b64encode(b'codeword').decode()]:
            self.assertEqual(self.request(auth=auth)[0],401)
    def test_exact_get_health_exception_only(self):
        status,headers,body=self.request('/healthz',host='healthcheck.railway.app')
        self.assertEqual(status,200);self.assertEqual(json.loads(body),{'ok':True})
        for path in ['/healthz?query=1','/healthz/','/%68ealthz']:
            self.assertEqual(self.request(path)[0],401)
        for method in ['POST','HEAD','OPTIONS']:
            self.assertEqual(self.request('/healthz',method)[0],401)
    def test_duplicate_security_headers_fail_closed(self):
        for name,value in [('Host','puzzle.example.test'),('Origin',ORIGIN),('Authorization',self.auth())]:
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            conn.putrequest('GET','/api/puzzles',skip_host=True)
            conn.putheader('Host','puzzle.example.test');conn.putheader('Authorization',self.auth())
            if name=='Origin':conn.putheader('Origin',ORIGIN)
            conn.putheader(name,value);conn.endheaders();response=conn.getresponse()
            self.assertIn(response.status,(401,403));response.read();conn.close()

    def test_spoofed_host_or_origin_fails_even_with_auth(self):
        for host in ['evil.test','puzzle.example.test.evil','puzzle.example.test:443','127.0.0.1']:
            self.assertEqual(self.request(auth=self.auth(),host=host)[0],403)
        for origin in ['https://evil.test','http://puzzle.example.test','null',ORIGIN+'/']:
            for method in ['GET','POST']:
                self.assertEqual(self.request('/api/puzzles',method,auth=self.auth(),origin=origin)[0],403)
        self.assertEqual(self.request('/api/puzzles',auth=self.auth(),origin=ORIGIN)[0],200)

class PublicAndLocalHTTPTests(unittest.TestCase):
    def test_explicit_public_opt_in_and_local_defaults(self):
        for options,host in [({'public_origin':ORIGIN,'allow_public':True},'puzzle.example.test'),({},None)]:
            with tempfile.TemporaryDirectory() as directory:
                server=make_server(0,directory,**options);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    self.assertEqual(server.server_address[0],'127.0.0.1')
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    conn.request('GET','/api/puzzles',headers={'Host':host or f'127.0.0.1:{server.server_port}'})
                    response=conn.getresponse();self.assertEqual(response.status,200);response.read();conn.close()
                finally:server.shutdown();server.server_close();thread.join()
