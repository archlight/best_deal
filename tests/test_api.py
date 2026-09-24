from fastapi.testclient import TestClient

from best_deal.api import create_app


def client(store):
    return TestClient(create_app(store))


def test_search_observe_insights_flow(store):
    c = client(store)
    r = c.post("/api/search", json={"origin": "Changi Airport T3", "destination": "Marina Bay Sands", "when": "2026-09-23T18:30"})
    assert r.status_code == 200
    body = r.json()
    q = body["quotes"][0]
    obs = c.post("/api/observations", json={"search_id": body["search_id"], "provider": q["provider"],
                                            "product": q["product"], "price": q["price"] + 1})
    assert obs.status_code == 201
    saved = c.get(f"/api/searches/{body['search_id']}").json()["quotes"]
    assert [x["source"] for x in saved].count("observed") == 1
    assert c.get("/api/searches").json()[0]["observed"] == 1
    ins = c.get("/api/insights").json()
    assert ins["summary"]["observed_quotes"] == 1
    csv = c.get("/api/export.csv")
    assert csv.status_code == 200 and csv.text.startswith("id,search_id")


def test_errors(store):
    c = client(store)
    assert c.post("/api/search", json={"origin": "nowhere-land", "destination": "Bugis"}).status_code == 400
    assert c.post("/api/observations", json={"search_id": 42, "provider": "Grab", "product": "JustGrab", "price": 9}).status_code == 404
    assert c.post("/api/observations", json={"search_id": 1, "provider": "Grab", "product": "JustGrab", "price": -1}).status_code == 422
    assert c.get("/api/insights?source=bogus").status_code == 422


def test_timeline_places_and_ui(store):
    c = client(store)
    t = c.post("/api/timeline", json={"origin": "Bugis", "destination": "Novena", "hours": 2}).json()
    assert len(t["slots"]) >= 4
    assert c.get("/api/places?q=chan").json()[0]["name"].startswith("Changi")
    assert "best<b>deal</b>" in c.get("/").text
    assert c.get("/static/app.js").status_code == 200


def test_password_protects_everything_but_health(store):
    c = TestClient(create_app(store, password="s3cret"))
    assert c.get("/healthz").status_code == 200
    denied = c.get("/api/providers")
    assert denied.status_code == 401 and "Basic" in denied.headers["www-authenticate"]
    assert c.get("/api/providers", auth=("me", "wrong")).status_code == 401
    assert c.get("/api/providers", auth=("me", "s3cret")).status_code == 200
    assert c.get("/", auth=("anyone", "s3cret")).status_code == 200
