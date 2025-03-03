from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker, declarative_base

# Correcting the DATABASE_URL with the password included
DATABASE_URL = "postgresql://admin:yourpassword@localhost:5432/guestdb"

# Creating the SQLAlchemy engine with a connection pool for multithreading
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=0)

# Session local to bind the engine for transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()
