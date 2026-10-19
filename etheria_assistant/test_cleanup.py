"""Enforce Windows log-file deletion rules even when tests run on Linux."""
import logging
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import test_data


class WindowsCleanupTests(unittest.TestCase):
    def test_legacy_migration_closes_logs_before_removing_temp_directory(self):
        streams=[];removed=[]
        original_open=logging.FileHandler._open
        original_rmtree=shutil.rmtree

        def tracked_open(handler):
            stream=original_open(handler);streams.append(stream);return stream

        def windows_rmtree(path,*args,**kwargs):
            root=Path(path).resolve()
            for stream in streams:
                if not stream.closed and Path(stream.name).resolve().is_relative_to(root):
                    raise PermissionError('Windows deletion rule: log file still open')
            removed.append(root)
            return original_rmtree(path,*args,**kwargs)

        case=test_data.DataTests('test_legacy_database_migration_context_backup_and_export')
        result=unittest.TestResult()
        with patch.object(logging.FileHandler,'_open',tracked_open),patch.object(shutil,'rmtree',windows_rmtree):
            case.run(result)
        self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
        self.assertGreaterEqual(len(streams),2)
        self.assertTrue(removed)
        self.assertTrue(all(stream.closed for stream in streams))


if __name__=='__main__':unittest.main()
