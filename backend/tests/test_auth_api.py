class TestAuth:
    async def test_register_login_me_roundtrip(self, client):
        email = "roundtrip@example.com"
        r = await client.post("/auth/register",
                              json={"email": email, "password": "supersecret1"})
        assert r.status_code == 201
        assert "access_token" in r.json()

        r = await client.post("/auth/login",
                              json={"email": email, "password": "supersecret1"})
        assert r.status_code == 200
        token = r.json()["access_token"]

        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == email

    async def test_duplicate_email_rejected(self, client):
        email = "dupe@example.com"
        await client.post("/auth/register", json={"email": email, "password": "supersecret1"})
        r = await client.post("/auth/register", json={"email": email, "password": "supersecret1"})
        assert r.status_code == 400

    async def test_wrong_password_401(self, client):
        email = "wrongpw@example.com"
        await client.post("/auth/register", json={"email": email, "password": "supersecret1"})
        r = await client.post("/auth/login", json={"email": email, "password": "not-it-at-all"})
        assert r.status_code == 401

    async def test_me_requires_token(self, client):
        r = await client.get("/auth/me")
        assert r.status_code == 401

    async def test_garbage_token_401(self, client):
        r = await client.get("/auth/me", headers={"Authorization": "Bearer nonsense"})
        assert r.status_code == 401

    async def test_refresh_flow(self, client):
        r = await client.post("/auth/register",
                              json={"email": "refresh@example.com", "password": "supersecret1"})
        refresh = r.json()["refresh_token"]
        r = await client.post("/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200
        assert r.json()["access_token"]

    async def test_access_token_rejected_as_refresh(self, client):
        r = await client.post("/auth/register",
                              json={"email": "types@example.com", "password": "supersecret1"})
        access = r.json()["access_token"]
        r = await client.post("/auth/refresh", json={"refresh_token": access})
        assert r.status_code == 401

    async def test_register_creates_default_alert_rules(self, auth_client):
        r = await auth_client.get("/alerts/rules")
        assert r.status_code == 200
        assert {rule["rule_type"] for rule in r.json()} == {
            "top20_entry", "relvol_3x", "breakout", "rsi_cross_50", "unusual_options"}
