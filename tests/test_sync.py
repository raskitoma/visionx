import pytest
import os

os.environ["SOURCE_DBS"] = "AV3:AV3@10.102.6.11:3306|Line1,AV3:AV3@10.102.6.12:3307|Line2"
os.environ["TARGET_DB"] = "syncuser:syncpwd@target-db:3306/target"

from app.config import parse_source_dbs, parse_target_db

def test_parse_source_dbs():
    raw = os.environ["SOURCE_DBS"]
    sources = parse_source_dbs(raw)
    assert len(sources) == 2
    assert sources[0]["line"] == "Line1"
    assert sources[0]["user"] == "AV3"
    assert sources[0]["host"] == "10.102.6.11"
    assert sources[0]["port"] == 3306

def test_parse_target_db():
    raw = os.environ["TARGET_DB"]
    target = parse_target_db(raw)
    assert target is not None
    assert target["user"] == "syncuser"
    assert target["database"] == "target"
