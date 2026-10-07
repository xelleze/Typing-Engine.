from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.typing.rare_store import RareWordStore
from app.typing.timing_engine import TimingEngine


class StorageTests(unittest.TestCase):
    def test_sparse_storage_persists_and_adapts(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'rare.sqlite'
            with RareWordStore(path) as store:
                store.record('the', 7.73)
                store.record('borderline', 3.5)
                self.assertEqual(store.seen_count('the'), 0)
                self.assertEqual(store.seen_count('borderline'), 0)
                before = TimingEngine(seed=1, store=store).explain('onychophora')
                for _ in range(50):
                    store.record('Onychophora', 0)
                after = TimingEngine(seed=1, store=store).explain('onychophora')
                self.assertLess(after[0]['planning_delay'], before[0]['planning_delay'] / 10)
                self.assertEqual(before[0]['motor_ms'], after[0]['motor_ms'])
                self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM rare_words').fetchone()[0], 1)
            with RareWordStore(path) as store:
                self.assertEqual(store.seen_count('ONYCHOPHORA'), 50)

    def test_preview_does_not_record_encounters(self):
        with TemporaryDirectory() as directory:
            with RareWordStore(Path(directory) / 'rare.sqlite') as store:
                TimingEngine(store=store).generate('onychophora')
                self.assertEqual(store.seen_count('onychophora'), 0)
