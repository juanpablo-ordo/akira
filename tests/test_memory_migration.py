"""Migration releases real database handles before Windows removes staged files."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge import KnowledgeStore
from migrate_v11_settings import merge_memory


class MemoryMigrationHandleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = KnowledgeStore(self.root / 'original')
        self.source.remember('user', 'Recuperar memoria de Akira, también con acentos.')
        self.target = self.root / 'candidate' / 'state' / 'knowledge.sqlite3'
        self.connections = []
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            self.connections.append(connection)
            self.addCleanup(connection.close)
            return connection

        self.track = patch('migrate_v11_settings.sqlite3.connect', side_effect=connect)

    def assert_handles_released(self):
        # Retain the connections so garbage collection cannot mask an open handle.
        self.assertTrue(self.connections)
        for connection in self.connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')

    def test_new_copy_releases_both_handles_and_preserves_history(self):
        with self.track:
            report = merge_memory(self.source.path, self.target)
        self.assertTrue(report['copied'])
        self.assertEqual(len(self.connections), 2)
        self.assert_handles_released()
        self.assertEqual(KnowledgeStore(self.root / 'candidate').history(), self.source.history())

    def test_existing_merge_releases_handles_commits_and_deduplicates(self):
        destination = KnowledgeStore(self.root / 'candidate')
        destination.remember('assistant', 'Memoria actual')
        with self.track:
            first = merge_memory(self.source.path, self.target)
            second = merge_memory(self.source.path, self.target)
        self.assertEqual((first['turns'], second['turns']), (1, 0))
        self.assertEqual(len(destination.history()), 2)
        self.assert_handles_released()

    def test_merge_failure_rolls_back_and_releases_both_handles(self):
        destination = KnowledgeStore(self.root / 'candidate')
        destination.remember('assistant', 'Memoria vigente')
        row = {'url': 'https://example.org/a', 'fetched': 2, 'body': 'fuente'}
        self.source.put(row)
        destination.put({**row, 'fetched': 1})
        with self.source.db() as connection:
            connection.execute("UPDATE sources SET fetched='valor inválido'")
        before = destination.history()
        with self.track, self.assertRaises(ValueError):
            merge_memory(self.source.path, self.target)
        self.assert_handles_released()
        self.assertEqual(destination.history(), before)
        self.assertEqual(destination.get(row['url'])['fetched'], 1)

    def test_destination_open_failure_still_releases_source(self):
        self.target.mkdir(parents=True)
        with self.track, self.assertRaises(sqlite3.OperationalError):
            merge_memory(self.source.path, self.target)
        self.assertEqual(len(self.connections), 1)
        self.assert_handles_released()

    def test_corrupt_source_releases_both_handles(self):
        self.source.path.write_bytes(b'not a SQLite database')
        with self.track, self.assertRaises(sqlite3.DatabaseError):
            merge_memory(self.source.path, self.target)
        self.assertEqual(len(self.connections), 2)
        self.assert_handles_released()

    def test_same_file_is_never_opened_or_overwritten(self):
        with self.track:
            result = merge_memory(self.source.path, self.source.path)
        self.assertEqual(result, {'copied': False})
        self.assertEqual(self.connections, [])


if __name__ == '__main__':
    unittest.main()
