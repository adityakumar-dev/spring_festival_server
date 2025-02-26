from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://admin@localhost:5432/guestdb"

engine = create_engine(DATABASE_URL, connect_args={"password": "yourpassword"})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

