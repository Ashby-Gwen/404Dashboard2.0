from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import os


load_dotenv()


def build_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    user = os.getenv("user")
    password = os.getenv("password")
    host = os.getenv("host")
    port = os.getenv("port")
    dbname = os.getenv("dbname")

    missing = [
        name
        for name, value in {
            "user": user,
            "password": password,
            "host": host,
            "port": port,
            "dbname": dbname,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing database environment values: {', '.join(missing)}")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


engine = create_engine(build_database_url(), pool_pre_ping=True, pool_recycle=300)


try:
    with engine.connect() as connection:
        connection.execute(text("select 1"))
        print("Connection successful!")
except Exception as e:
    print(f"Failed to connect: {e}")
