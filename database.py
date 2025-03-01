from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Correcting the DATABASE_URL with the password included
DATABASE_URL = "postgresql://admin:yourpassword@localhost:5432/guestdb"

# Creating the SQLAlchemy engine
engine = create_engine(DATABASE_URL)

# Session local to bind the engine for transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()
