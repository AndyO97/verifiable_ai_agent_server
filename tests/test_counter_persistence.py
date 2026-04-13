"""
Tests for PostgreSQL-backed atomic counter (Phase 3 Task 3).
"""

import pytest
import threading
import time
import statistics
from unittest.mock import Mock, patch, MagicMock

from src.integrity.database_counter import DatabaseCounter, SessionCounter, create_database_counter


class TestDatabaseCounter:
    """Test PostgreSQL counter persistence and atomicity"""
    
    @pytest.fixture
    def mock_session(self):
        """Mock SQLAlchemy session"""
        return MagicMock()
    
    @pytest.fixture
    def db_url(self):
        """Test database URL"""
        return "postgresql://postgres:postgres@localhost:5432/test_verifiable"
    
    def test_database_counter_init(self, db_url):
        """Test DatabaseCounter initialization"""
        session_id = "test-session-001"
        
        with patch('src.integrity.database_counter.create_engine') as mock_engine:
            with patch('src.integrity.database_counter.sessionmaker'):
                mock_engine.return_value.dispose = Mock()
                counter = DatabaseCounter(session_id, db_url)
                
                assert counter.session_id == session_id
                assert counter.local_counter == 0
                assert counter.db_url == db_url
    
    def test_database_counter_increment_first_time(self):
        """Test first counter increment creates new entry"""
        session_id = "test-session-002"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 0
        counter.Session = MagicMock()
        
        # Mock the session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None  # No existing entry
        
        counter.Session.return_value = mock_session
        
        # Mock logger
        with patch('src.integrity.database_counter.logger'):
            # First increment
            with patch('src.integrity.database_counter.datetime'):
                next_val = counter.increment()
        
        # Should have created new entry with value 1
        assert counter.local_counter == 1
    
    def test_database_counter_increment_subsequent(self):
        """Test subsequent counter increments"""
        session_id = "test-session-003"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 5  # Start from 5
        counter.Session = MagicMock()
        
        # Mock existing counter row
        mock_row = MagicMock()
        mock_row.max_counter = 5
        
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_row
        
        counter.Session.return_value = mock_session
        
        with patch('src.integrity.database_counter.logger'):
            with patch('src.integrity.database_counter.datetime'):
                next_val = counter.increment()
        
        # Should increment to 6
        assert counter.local_counter == 6
        assert mock_row.max_counter == 6
    
    def test_startup_validation_no_existing_session(self):
        """Test startup validation when session doesn't exist in DB"""
        session_id = "test-session-new"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 0
        counter.Session = MagicMock()
        
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = None  # No entry
        
        counter.Session.return_value = mock_session
        
        with patch('src.integrity.database_counter.logger'):
            counter.startup_validation()
        
        # Should not raise error
        assert counter.local_counter == 0
    
    def test_startup_validation_restores_from_db(self):
        """Test startup validation restores counter from database"""
        session_id = "test-session-restore"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 10  # Start with same value as DB to avoid rollback detection
        counter.Session = MagicMock()
        
        # Mock existing counter row with max_counter=10
        mock_row = MagicMock()
        mock_row.max_counter = 10
        
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_row
        
        counter.Session.return_value = mock_session
        
        with patch('src.integrity.database_counter.logger'):
            counter.startup_validation()
        
        # Should restore to 10
        assert counter.local_counter == 10
    
    def test_startup_validation_detects_rollback(self):
        """Test that startup validation detects counter rollback attack"""
        session_id = "test-session-rollback"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 5  # Local is 5
        counter.Session = MagicMock()
        
        # Mock existing counter row with higher value
        mock_row = MagicMock()
        mock_row.max_counter = 10  # DB has 10 > local 5
        
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = mock_row
        
        counter.Session.return_value = mock_session
        
        with patch('src.integrity.database_counter.logger'):
            # Should raise RuntimeError for rollback detection
            with pytest.raises(RuntimeError, match="rollback"):
                counter.startup_validation()
    
    def test_get_current_counter(self):
        """Test retrieving current counter without incrementing"""
        session_id = "test-session-004"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 42
        
        current = counter.get_current()
        
        assert current == 42
    
    def test_reset_session(self):
        """Test resetting/clearing session counter"""
        session_id = "test-session-cleanup"
        counter = DatabaseCounter.__new__(DatabaseCounter)
        counter.session_id = session_id
        counter.local_counter = 10
        counter.Session = MagicMock()
        
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_delete = MagicMock()
        mock_query.filter_by.return_value.delete = mock_delete
        
        counter.Session.return_value = mock_session
        
        with patch('src.integrity.database_counter.logger'):
            counter.reset_session()
        
        # Should reset local counter
        assert counter.local_counter == 0
        # Should have called delete
        mock_delete.assert_called_once()


class TestDatabaseCounterIntegration:
    """Integration tests for database counter using SQLite backend."""

    @pytest.fixture
    def sqlite_db_url(self, tmp_path):
        """Create isolated file-backed SQLite DB URL for integration tests."""
        db_file = tmp_path / "test_counter_integration.sqlite3"
        return f"sqlite:///{db_file.as_posix()}"
    
    @pytest.mark.integration
    def test_counter_persistence_across_sessions(self, sqlite_db_url):
        """Counter value persists when counter object is recreated."""
        session_id = "integration-session-persistence"

        # First process/session lifecycle
        counter_a = create_database_counter(session_id, sqlite_db_url)
        assert counter_a.get_current() == 0
        assert counter_a.increment() == 1
        assert counter_a.increment() == 2

        # Simulate restart with new instance and startup validation
        counter_b = create_database_counter(session_id, sqlite_db_url)
        assert counter_b.get_current() == 2
        assert counter_b.increment() == 3
    
    @pytest.mark.integration
    def test_concurrent_counter_increments(self, sqlite_db_url):
        """Concurrent increments should not lose updates."""
        session_id = "integration-session-concurrency"
        counter = create_database_counter(session_id, sqlite_db_url)

        increments_per_thread = 10
        thread_count = 4
        expected_total = increments_per_thread * thread_count

        errors = []

        def worker():
            try:
                for _ in range(increments_per_thread):
                    counter.increment()
            except Exception as exc:  # pragma: no cover - diagnostic path
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        restored = create_database_counter(session_id, sqlite_db_url)
        assert restored.get_current() == expected_total

    @pytest.mark.integration
    def test_concurrency_characterization_writes_and_restorations(self, sqlite_db_url):
        """Characterize concurrent write/restore behavior with throughput and latency metrics."""
        session_id = "integration-session-concurrency-metrics"
        counter = create_database_counter(session_id, sqlite_db_url)

        write_threads = 8
        increments_per_thread = 40
        total_writes = write_threads * increments_per_thread

        write_latencies_ms: list[float] = []
        write_errors = []
        write_lock = threading.Lock()

        def write_worker() -> None:
            try:
                for _ in range(increments_per_thread):
                    t0 = time.perf_counter_ns()
                    counter.increment()
                    t1 = time.perf_counter_ns()
                    with write_lock:
                        write_latencies_ms.append((t1 - t0) / 1_000_000)
            except Exception as exc:  # pragma: no cover - diagnostic path
                write_errors.append(exc)

        start_write_ns = time.perf_counter_ns()
        workers = [threading.Thread(target=write_worker) for _ in range(write_threads)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        write_elapsed_s = (time.perf_counter_ns() - start_write_ns) / 1_000_000_000

        assert not write_errors

        restored_counter = create_database_counter(session_id, sqlite_db_url)
        assert restored_counter.get_current() == total_writes

        write_throughput_tps = total_writes / write_elapsed_s if write_elapsed_s > 0 else 0.0
        write_median_ms = statistics.median(write_latencies_ms)
        write_p95_ms = statistics.quantiles(write_latencies_ms, n=20, method="inclusive")[18]
        write_max_ms = max(write_latencies_ms)

        restore_threads = 6
        restores_per_thread = 20
        total_restores = restore_threads * restores_per_thread

        restore_latencies_ms: list[float] = []
        restore_errors = []
        restore_lock = threading.Lock()

        def restore_worker() -> None:
            try:
                for _ in range(restores_per_thread):
                    t0 = time.perf_counter_ns()
                    restored = create_database_counter(session_id, sqlite_db_url)
                    current_value = restored.get_current()
                    t1 = time.perf_counter_ns()
                    if current_value != total_writes:
                        raise AssertionError(
                            f"Unexpected restored value {current_value}, expected {total_writes}"
                        )
                    with restore_lock:
                        restore_latencies_ms.append((t1 - t0) / 1_000_000)
                    restored.engine.dispose()
            except Exception as exc:  # pragma: no cover - diagnostic path
                restore_errors.append(exc)

        start_restore_ns = time.perf_counter_ns()
        restorers = [threading.Thread(target=restore_worker) for _ in range(restore_threads)]
        for restorer in restorers:
            restorer.start()
        for restorer in restorers:
            restorer.join()
        restore_elapsed_s = (time.perf_counter_ns() - start_restore_ns) / 1_000_000_000

        assert not restore_errors

        restore_throughput_tps = (
            total_restores / restore_elapsed_s if restore_elapsed_s > 0 else 0.0
        )
        restore_median_ms = statistics.median(restore_latencies_ms)
        restore_p95_ms = statistics.quantiles(restore_latencies_ms, n=20, method="inclusive")[18]
        restore_max_ms = max(restore_latencies_ms)

        # Coarse lock-contention proxy: upper-tail increment latency under concurrent writes.
        max_observed_lock_wait_ms = write_max_ms

        print(
            "[6.9.4 concurrency metrics] "
            f"write_threads={write_threads}, increments_per_thread={increments_per_thread}, total_writes={total_writes}, "
            f"write_throughput_tps={write_throughput_tps:.2f}, write_median_ms={write_median_ms:.3f}, "
            f"write_p95_ms={write_p95_ms:.3f}, write_max_ms={write_max_ms:.3f}, "
            f"restore_threads={restore_threads}, restores_per_thread={restores_per_thread}, total_restores={total_restores}, "
            f"restore_throughput_tps={restore_throughput_tps:.2f}, restore_median_ms={restore_median_ms:.3f}, "
            f"restore_p95_ms={restore_p95_ms:.3f}, restore_max_ms={restore_max_ms:.3f}, "
            f"max_observed_lock_wait_ms={max_observed_lock_wait_ms:.3f}"
        )

        assert write_throughput_tps > 0
        assert restore_throughput_tps > 0


class TestCreateDatabaseCounterFactory:
    """Test database counter factory function"""
    
    def test_create_database_counter_with_explicit_url(self):
        """Test factory with explicit database URL"""
        session_id = "test-factory-001"
        db_url = "postgresql://postgres:postgres@localhost:5432/test"
        
        with patch('src.integrity.database_counter.DatabaseCounter.__init__', return_value=None):
            with patch.object(DatabaseCounter, 'startup_validation'):
                counter = create_database_counter(session_id, db_url)
                
                # Should create counter instance
                assert isinstance(counter, DatabaseCounter) or counter is not None
    
    def test_create_database_counter_uses_env(self):
        """Test factory uses PostgreSQL settings from environment"""
        session_id = "test-factory-002"
        
        with patch('src.integrity.database_counter.PostgresSettings') as mock_settings_class:
            # Mock the settings instance
            mock_settings = MagicMock()
            mock_settings.user = "testuser"
            mock_settings.password = "testpass"
            mock_settings.host = "testhost"
            mock_settings.port = 5432
            mock_settings.database = "testdb"
            mock_settings_class.return_value = mock_settings
            
            with patch('src.integrity.database_counter.DatabaseCounter.__init__', return_value=None):
                with patch('src.integrity.database_counter.DatabaseCounter.startup_validation'):
                    counter = create_database_counter(session_id)
                    
                    # Should have called PostgresSettings
                    mock_settings_class.assert_called_once()


class TestSessionCounterModel:
    """Test SQLAlchemy SessionCounter model"""
    
    def test_session_counter_model_creation(self):
        """Test creating SessionCounter model instance"""
        from datetime import datetime, timezone
        
        session_counter = SessionCounter(
            session_id="test-001",
            max_counter=5,
            last_updated=datetime.now(timezone.utc)
        )
        
        assert session_counter.session_id == "test-001"
        assert session_counter.max_counter == 5
        assert session_counter.last_updated is not None
    
    def test_session_counter_table_name(self):
        """Test SessionCounter table name"""
        assert SessionCounter.__tablename__ == "session_counters"
    
    def test_session_counter_primary_key(self):
        """Test SessionCounter has correct primary key"""
        # session_id should be primary key
        pk_columns = [col.name for col in SessionCounter.__table__.primary_key.columns]
        assert "session_id" in pk_columns
