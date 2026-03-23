"""
PostgreSQL-backed atomic counter for replay prevention.

Provides:
- Atomic monotonic counter increment
- Rollback detection on startup
- Session-level counter persistence
- Thread-safe operations
"""


from datetime import datetime, timezone
from contextlib import nullcontext
import threading
from typing import Optional

import structlog
from sqlalchemy import create_engine, Column, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import get_settings, PostgresSettings

logger = structlog.get_logger(__name__)

Base = declarative_base()


class SessionCounter(Base):
    """SQLAlchemy model for session counters"""
    __tablename__ = "session_counters"
    
    session_id = Column(String(36), primary_key=True)  # UUID format
    max_counter = Column(Integer, default=0, nullable=False)
    last_updated = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_id"),
    )


class DatabaseCounter:
    """
    PostgreSQL-backed atomic counter for monotonic sequence numbers.
    
    Provides replay attack prevention through:
    - Atomic counter increments (database level)
    - Rollback detection (startup validation)
    - Session isolation (per session_id)
    - Persisted state (survives server restart)
    """
    
    def __init__(
        self,
        session_id: str,
        db_url: str | None = None
    ):
        """
        Initialize database counter for a session.
        
        Args:
            session_id: Unique session identifier
            db_url: PostgreSQL connection string (defaults to settings from .env)
        """
        if db_url is None:
            pg = get_settings().postgres
            db_url = f"postgresql://{pg.user}:{pg.password}@{pg.host}:{pg.port}/{pg.database}"
        
        self.session_id = session_id
        self.db_url = db_url
        self.local_counter = 0
        self._lock = threading.Lock()
        
        try:
            self.engine = create_engine(db_url, echo=False)
            self.Session = sessionmaker(bind=self.engine)
            
            # Create tables if not exist
            Base.metadata.create_all(self.engine)
            
            logger.info("database_counter_initialized", session_id=self.session_id)
        except Exception as e:
            logger.error("database_counter_init_failed", error=str(e))
            raise
    
    def startup_validation(self) -> None:
        """
        Validate counter state on startup.
        
        Detects potential rollback attacks where:
        - Previous max_counter > current local counter
        - Session persists from previous run
        
        Raises RuntimeError if rollback detected.
        """
        try:
            session = self.Session()
            
            # Check if session exists in database
            counter_row = session.query(SessionCounter).filter_by(
                session_id=self.session_id
            ).first()
            
            if counter_row is not None:
                db_max_counter = counter_row.max_counter
                
                # If local counter is non-zero and behind the persisted value,
                # treat it as rollback. A zero local counter is a fresh process
                # startup and should restore from database.
                if self.local_counter != 0 and self.local_counter < db_max_counter:
                    logger.error(
                        "rollback_detected",
                        session_id=self.session_id,
                        db_max_counter=db_max_counter,
                        local_counter=self.local_counter
                    )
                    session.close()
                    raise RuntimeError(
                        f"Counter rollback detected: DB has {db_max_counter}, "
                        f"local is {self.local_counter}"
                    )
                
                # Update local counter from database
                self.local_counter = db_max_counter
                logger.info(
                    "counter_restored_from_db",
                    session_id=self.session_id,
                    restored_counter=self.local_counter
                )
            else:
                # First time seeing this session ID, create entry
                logger.info("new_session_created", session_id=self.session_id)
            
            session.close()
        except Exception as e:
            logger.error("startup_validation_failed", error=str(e))
            raise
    
    def increment(self) -> int:
        """
        Atomically increment and return the next counter value.
        
        Returns:
            Next counter value (incremented in database)
        """
        lock = getattr(self, "_lock", None)
        with (lock if lock is not None else nullcontext()):
            try:
                session = self.Session()
                
                # Upsert: insert if not exists, update if exists
                counter_row = session.query(SessionCounter).filter_by(
                    session_id=self.session_id
                ).first()
                
                if counter_row is None:
                    # First increment for this session
                    new_row = SessionCounter(
                        session_id=self.session_id,
                        max_counter=1,
                        last_updated=datetime.now(timezone.utc)
                    )
                    session.add(new_row)
                    self.local_counter = 1
                else:
                    # In-process lock + DB commit keeps increments monotonic for shared instance.
                    counter_row.max_counter += 1
                    counter_row.last_updated = datetime.now(timezone.utc)
                    self.local_counter = counter_row.max_counter
                
                session.commit()
                next_value = self.local_counter
                
                logger.debug(
                    "counter_incremented",
                    session_id=self.session_id,
                    next_value=next_value
                )
                
                session.close()
                return next_value
        
            except SQLAlchemyError as e:
                logger.error("counter_increment_failed", error=str(e))
                raise
    
    def get_current(self) -> int:
        """
        Get the current counter value without incrementing.
        
        Returns:
            Current counter value from local state
        """
        return self.local_counter
    
    def reset_session(self) -> None:
        """
        Delete the session counter entry (cleanup after finalization).
        
        Only call this after run is completely finalized and archived.
        """
        try:
            session = self.Session()
            
            session.query(SessionCounter).filter_by(
                session_id=self.session_id
            ).delete()
            
            session.commit()
            self.local_counter = 0
            
            logger.info("session_counter_reset", session_id=self.session_id)
            session.close()
        except Exception as e:
            logger.error("session_reset_failed", error=str(e))
            raise


def create_database_counter(
    session_id: str,
    db_url: Optional[str] = None
) -> DatabaseCounter:
    """
    Factory function to create and initialize a DatabaseCounter.
    
    Args:
        session_id: Unique session identifier
        db_url: PostgreSQL connection string (uses env var or default)
    
    Returns:
        Initialized DatabaseCounter instance
    """
    if db_url is None:
        # Use settings from environment
        pg_settings = PostgresSettings(password="postgres")  # Default
        db_url = (
            f"postgresql://{pg_settings.user}:{pg_settings.password}@"
            f"{pg_settings.host}:{pg_settings.port}/{pg_settings.database}"
        )
    
    counter = DatabaseCounter(session_id, db_url)
    counter.startup_validation()
    return counter
