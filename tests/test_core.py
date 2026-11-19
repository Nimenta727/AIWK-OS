import tempfile
import unittest
from pathlib import Path
from aiws.router import recommend
from aiws.store import Store


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))
        self.store.create_project('example')

    def tearDown(self):
        self.temp.cleanup()

    def test_route(self):
        self.assertEqual(recommend('架构分析', '')['agent'], 'claude')
        self.assertEqual(recommend('修复测试', '')['agent'], 'codex')
        self.assertEqual(recommend('架构设计和代码重构', '')['agent'], 'dual')
        self.assertEqual(recommend('问候', '')['agent'], 'manual')

    def test_reject_path_traversal(self):
        for value in ('../outside', '..', 'x/y', 'x\\y', '', '.hidden/../hello', 'semi;colon'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.project_path(value)

    def test_symlink_escape(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        link = self.store.projects_root / 'escape'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest('symlinks not supported')
        with self.assertRaises(ValueError):
            self.store.project_path('escape')
        self.assertNotIn('escape',self.store.projects())

    def test_create_prepare_persist(self):
        task = self.store.create_task('分析','请列出问题','example','claude','分析任务')
        self.assertEqual(task['status'],'pending')
        brief = self.store.task_brief(task['id'])
        self.assertTrue(brief.is_file())
        self.assertIn('docs/routine/',brief.read_text('utf-8'))
        self.assertEqual(Store(Path(self.temp.name)).get(task['id'])['status'],'prepared')

    def test_windows_reserved_names(self):
        for value in ("CON", "nul", "COM1", "LPT9", "aux.txt", "folder."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.create_project(value)

    def test_recover_interrupted_tasks(self):
        t = self.store.create_task('Run', '', 'example', 'codex', '')
        self.store.update(t['id'], 'running')
        recovered = Store(Path(self.temp.name)).get(t['id'])
        self.assertEqual(recovered['status'], 'failed')
        self.assertIn('中断', recovered['result'])

    def test_limit(self):
        with self.assertRaises(ValueError):
            self.store.create_task('X'*141,'','example','codex','')
        with self.assertRaises(ValueError):
            self.store.create_task('okay','hello','../invalid','codex','')

if __name__ == '__main__':
    unittest.main()
