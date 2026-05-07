import traceback
from starlette.testclient import TestClient
import main

client = TestClient(main.app)
try:
    r = client.get('/products')
    print('STATUS', r.status_code)
    print(r.text[:2000])
except Exception:
    traceback.print_exc()
