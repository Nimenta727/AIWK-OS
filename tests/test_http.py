import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from aiws.server import make_server


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.temp.name),0)
        self.port = self.server.server_port
        self.t = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.t.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.t.join(timeout=5)
        self.temp.cleanup()

    def req(self,method,path,obj=None,token=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers=headers or {}
        if obj is not None:
            headers['Content-Type']='application/json'
            body=json.dumps(obj).encode('utf-8')
        else:
            body=None
        if token is not None: headers['X-AIWS-Token']=token
        conn.request(method,path,body,headers)
        res=conn.getresponse(); out=res.read(); status=res.status; conn.close()
        return status,json.loads(out)

    def test_endpoints_and_csrf(self):
        status,session=self.req('GET','/api/session')
        self.assertEqual(status,200)
        token=session['csrf']
        status,_=self.req('POST','/api/projects',{'name':'demo'})
        self.assertEqual(status,403)
        status,_=self.req('POST','/api/projects',{'name':'demo'},token)
        self.assertEqual(status,201)
        status,_=self.req('POST','/api/tasks',{'title':'代码测试','description':'只读','project':'demo','agent':'auto'},token)
        self.assertEqual(status,201)
        status,tasks=self.req('GET','/api/tasks')
        self.assertEqual(len(tasks['tasks']),1)
        task_id=tasks['tasks'][0]['id']
        status,j=self.req('POST',f'/api/tasks/{task_id}/prepare',{},token)
        self.assertEqual(status,200)
        self.assertIn('brief',j)
        status,_=self.req('POST',f'/api/tasks/{task_id}/codex-readonly',{'confirmed':True},token)
        self.assertEqual(status,403)

    def test_workflow_http_gates(self):
        _,session = self.req('GET','/api/session')
        token = session['csrf']
        self.req('POST','/api/projects',{'name':'demo'},token)
        _,response = self.req('POST','/api/tasks',
            {'title':'架构设计与重构测试','description':'一阶段分析二阶段实现','project':'demo','agent':'dual'},token)
        task_id = response['task']['id']
        _,all_tasks = self.req('GET','/api/tasks')
        self.assertEqual(len(all_tasks['tasks'][0]['steps']),3)
        status,_ = self.req('POST',f'/api/tasks/{task_id}/step-finish',
            {'state':'done','result':'skip'},token)
        self.assertEqual(status,400)
        self.req('POST',f'/api/tasks/{task_id}/prepare',{},token)
        status,_ = self.req('POST',f'/api/tasks/{task_id}/launch',{'agent':'codex'},token)
        self.assertEqual(status,400)
        status,response = self.req('POST',f'/api/tasks/{task_id}/step-finish',
            {'state':'done','result':'design approved'},token)
        self.assertEqual(status,200)
        self.assertEqual(response['task']['status'],'pending')
        self.assertEqual(response['task']['steps'][0]['status'],'done')
        status,_ = self.req('POST',f'/api/tasks/{task_id}/codex-readonly',{'confirmed':True},token)
        self.assertEqual(status,400)
        status,_ = self.req('POST',f'/api/tasks/{task_id}/worktree',{'confirmed':False},token)
        self.assertEqual(status,400)

    def test_host_header_and_origin(self):
        status,_=self.req('GET','/api/tasks',headers={'Host':'untrusted.example'})
        self.assertEqual(status,403)
        _,s=self.req('GET','/api/session')
        status,_=self.req('POST','/api/projects',{'name':'evil'},s['csrf'],headers={'Origin':'https://evil.example'})
        self.assertEqual(status,403)

    def test_path_and_unknown_agent_rejected(self):
        _,s=self.req('GET','/api/session')
        status,_=self.req('POST','/api/projects',{'name':'../oops'},s['csrf'])
        self.assertEqual(status,400)
        self.req('POST','/api/projects',{'name':'demo'},s['csrf'])
        status,_=self.req('POST','/api/tasks',{'title':'test','description':'','project':'demo','agent':'arbitrary'},s['csrf'])
        self.assertEqual(status,400)

if __name__=='__main__':
    unittest.main()
